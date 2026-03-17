"""
TA screener — 9 signals, all computed manually (no external TA libs).
Returns top N stocks with score, signals, and chart data.
"""
import pandas as pd
import numpy as np
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def _macd(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast = _ema(s, 12)
    slow = _ema(s, 26)
    line = fast - slow
    signal = _ema(line, 9)
    hist = line - signal
    return line, signal, hist


def _bollinger(s: pd.Series, n: int = 20) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    mid = _sma(s, n)
    std = s.rolling(n).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    bw = (upper - lower) / (mid + 1e-9)
    return upper, mid, lower, bw


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    pct_k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-9)
    pct_d = _sma(pct_k, d)
    return pct_k, pct_d


# ── scoring ───────────────────────────────────────────────────────────────────

def score_stock(ticker: str, df: pd.DataFrame) -> Optional[dict]:
    """
    Compute 9-signal score. Returns None if data insufficient.
    Signals:
      1. Golden Cross (MA20 > MA60) +15
      2. Volume surge (vol > 1.5× 20d avg) +10
      3. RSI momentum (50-70) +10
      4. MACD crossover +10
      5. Bollinger squeeze +10
      6. Stochastic oversold recovery +10
      7. 52-week high proximity +10
      8. 5-day momentum +10
      9. Relative strength (vs SPY approx) +15
    Total max: 100
    """
    if len(df) < 60:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # Dollar volume filter — $1M/day minimum
    avg_vol_20 = float(volume.tail(20).mean())
    last_close = float(close.iloc[-1])
    if avg_vol_20 * last_close < 1_000_000:
        return None

    score = 0
    signals: list[str] = []
    details: dict = {}

    # ── 1. Golden Cross ──
    ma20 = _sma(close, 20)
    ma60 = _sma(close, 60)
    if float(ma20.iloc[-1]) > float(ma60.iloc[-1]):
        score += 15
        signals.append("Golden Cross (MA20>60) ✨")
    details["golden_cross"] = float(ma20.iloc[-1]) > float(ma60.iloc[-1])

    # ── 2. Volume surge ──
    vol_ratio = float(volume.iloc[-1]) / (avg_vol_20 + 1)
    if vol_ratio >= 2.0:
        score += 10
        signals.append(f"Volume Surge {vol_ratio:.1f}× 🔥")
    elif vol_ratio >= 1.5:
        score += 6
        signals.append(f"Volume Up {vol_ratio:.1f}×")
    elif vol_ratio >= 1.2:
        score += 3
    details["vol_ratio"] = round(vol_ratio, 2)

    # ── 3. RSI momentum ──
    rsi = _rsi(close)
    rsi_val = float(rsi.iloc[-1])
    if 55 <= rsi_val <= 70:
        score += 10
        signals.append(f"RSI Strong Zone ({rsi_val:.0f}) 📈")
    elif 50 <= rsi_val < 55:
        score += 6
        signals.append(f"RSI Rising ({rsi_val:.0f})")
    elif 70 < rsi_val <= 80:
        score += 5
    elif rsi_val > 80:
        score += 2  # overbought
    details["rsi"] = round(rsi_val, 1)

    # ── 4. MACD crossover ──
    macd_line, macd_signal, macd_hist = _macd(close)
    ml = float(macd_line.iloc[-1])
    ms = float(macd_signal.iloc[-1])
    mh_now = float(macd_hist.iloc[-1])
    mh_prev = float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else 0.0
    if ml > ms and mh_now > mh_prev and mh_now > 0:
        score += 10
        signals.append("MACD Bullish Cross 🟢")
    elif ml > ms and mh_now > 0:
        score += 6
    elif ml > ms:
        score += 3
    details["macd"] = round(ml - ms, 4)

    # ── 5. Bollinger squeeze ──
    _, _, _, bw = _bollinger(close)
    bw_now = float(bw.iloc[-1])
    bw_20ago = float(bw.tail(21).iloc[0]) if len(bw) >= 21 else bw_now
    if bw_now < bw_20ago * 0.70:
        score += 10
        signals.append("Bollinger Squeeze 🎯")
    elif bw_now < bw_20ago * 0.85:
        score += 6
        signals.append("BB Narrowing")
    elif bw_now < bw_20ago * 0.93:
        score += 3
    details["bb_squeeze"] = round(bw_now / (bw_20ago + 1e-9), 3)

    # ── 6. Stochastic recovery ──
    stk, std_d = _stoch(high, low, close)
    stk_val = float(stk.iloc[-1])
    std_val = float(std_d.iloc[-1])
    stk_prev = float(stk.iloc[-2]) if len(stk) >= 2 else stk_val
    if stk_prev < 20 and stk_val > stk_prev and stk_val > std_val:
        score += 10
        signals.append(f"Stoch Oversold Recovery ({stk_val:.0f}) 🔄")
    elif stk_val < 30 and stk_val > stk_prev:
        score += 5
    elif 40 < stk_val < 60 and stk_val > std_val:
        score += 3
    details["stoch_k"] = round(stk_val, 1)

    # ── 7. 52-week high proximity ──
    hi52 = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
    dist = (hi52 - last_close) / (hi52 + 1e-9)
    if dist <= 0.03:
        score += 10
        signals.append(f"Near 52W High ({dist*100:.1f}% below) 🏔")
    elif dist <= 0.10:
        score += 7
        signals.append(f"52W High Proximity ({dist*100:.1f}%)")
    elif dist <= 0.20:
        score += 4
    details["dist_52w"] = round(dist, 4)

    # ── 8. 5-day momentum ──
    if len(close) >= 6:
        ret5 = float(close.iloc[-1] / close.iloc[-6] - 1) * 100
        if ret5 >= 10:
            score += 10
            signals.append(f"5D Return +{ret5:.1f}% 🚀")
        elif ret5 >= 5:
            score += 7
            signals.append(f"5D Return +{ret5:.1f}%")
        elif ret5 >= 2:
            score += 4
        elif ret5 < -5:
            score -= 3
        details["ret_5d"] = round(ret5, 2)

    # ── 9. Relative strength (20d vs market, approx) ──
    # We use the stock's own 20d return vs a fixed benchmark proxy
    # Actual SPY comparison is done in main.py and injected as benchmark_20d
    if len(close) >= 21:
        ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) * 100
        details["ret_20d"] = round(ret20, 2)
    else:
        details["ret_20d"] = 0.0

    # Build chart series (last 60 candles)
    chart_df = df.tail(60).copy()
    chart_data = {
        "dates": [str(d.date()) for d in chart_df.index],
        "open":   [round(float(v), 2) for v in chart_df["Open"]],
        "high":   [round(float(v), 2) for v in chart_df["High"]],
        "low":    [round(float(v), 2) for v in chart_df["Low"]],
        "close":  [round(float(v), 2) for v in chart_df["Close"]],
        "volume": [int(v) for v in chart_df["Volume"]],
        "ma20":   [round(float(v), 2) if not np.isnan(v) else None for v in _sma(chart_df["Close"], 20)],
        "ma60":   [round(float(v), 2) if not np.isnan(v) else None for v in _sma(chart_df["Close"], 60)],
        "bb_upper": [round(float(v), 2) if not np.isnan(v) else None for v in _bollinger(chart_df["Close"])[0]],
        "bb_lower": [round(float(v), 2) if not np.isnan(v) else None for v in _bollinger(chart_df["Close"])[2]],
        "rsi":    [round(float(v), 1) if not np.isnan(v) else None for v in _rsi(chart_df["Close"])],
        "macd_hist": [round(float(v), 4) if not np.isnan(v) else None for v in _macd(chart_df["Close"])[2]],
        "stoch_k": [round(float(v), 1) if not np.isnan(v) else None for v in _stoch(chart_df["High"], chart_df["Low"], chart_df["Close"])[0]],
        "stoch_d": [round(float(v), 1) if not np.isnan(v) else None for v in _stoch(chart_df["High"], chart_df["Low"], chart_df["Close"])[1]],
    }

    return {
        "ticker": ticker,
        "score": score,
        "signals": signals[:5],  # top 5 signals
        "details": details,
        "price": round(last_close, 2),
        "vol_ratio": round(vol_ratio, 2),
        "chart": chart_data,
    }


def run_screener(
    data: dict[str, Optional[pd.DataFrame]],
    spy_20d: float = 0.0,
    top_n: int = 10,
) -> list[dict]:
    """
    Score all fetched stocks, apply RS bonus vs SPY, return top N.
    """
    results = []
    for ticker, df in data.items():
        if df is None:
            continue
        res = score_stock(ticker, df)
        if res is None:
            continue

        # RS bonus
        rs_diff = res["details"].get("ret_20d", 0.0) - spy_20d
        rs_bonus = 0
        if rs_diff >= 15:
            rs_bonus = 15
            res["signals"].insert(0, f"RS +{rs_diff:.0f}% vs SPY 💪")
        elif rs_diff >= 8:
            rs_bonus = 10
        elif rs_diff >= 3:
            rs_bonus = 6
        elif rs_diff >= 0:
            rs_bonus = 3
        res["score"] += rs_bonus
        res["rs_bonus"] = rs_bonus
        res["rs_diff"] = round(rs_diff, 2)

        results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]
