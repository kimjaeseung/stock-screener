"""
TA screener — 11 signals, all computed manually (no external TA libs).
Returns top N stocks with score, signals (dict), chart_data (reels format),
swing data (ATR-based), and full indicator chart (SPA format).

Leveraged/inverse ETFs are excluded at scoring time via heuristic ATR check.
Definitive ETF-type filtering is done in run.py via yfinance info.
"""
import pandas as pd
import numpy as np
from typing import Optional


# ── 레버리지 ETF 블랙리스트 (하드코딩 + 휴리스틱) ─────────────────────────

# 알려진 2x/3x 레버리지·인버스 ETF 티커
LEVERAGED_BLACKLIST: set[str] = {
    # ProShares 2x/3x
    "UPRO","SPXL","TQQQ","SSO","QLD","UDOW","MVV","SAA","UWM","UXI","UYG",
    "URE","ROM","UGE","RXL","DIG","LTL","UBT","UCO","AGQ","YCL","EZJ",
    "EET","UBR","DDM",
    # ProShares inverse
    "SQQQ","SPXU","SPXS","SDS","QID","SDOW","MZZ","TWM","SDD","SRS","REW",
    "SKF","SZK","RXD","DUG","SMN","TBT","SCO","ZSL","YCS","EUO","BZQ",
    "EEV","EFU","FXP","EPV","DXD","DOG","PSQ",
    # Direxion 3x
    "TECL","TECS","SOXL","SOXS","LABU","LABD","FAS","FAZ","TNA","TZA",
    "NUGT","DUST","JNUG","JDST","NAIL","DFEN","WEBL","WEBS","WANT","RETL",
    "MIDU","MIDZ","DPST","CURE","HIBL","HIBS","INDL","DRN","DRV","ERX","ERY",
    "CLAW","TPOR","MEXX","BRZU","EURL","RUSL","RUSS",
    # GraniteShares 2x (single-stock)
    "NVDX","NVDD","AAPB","AAPD","METX","METD","AMZX","AMZD",
    "MSFX","MSFD","GOOGX","GOOGD","TSLL","TSLS","TSLQ","NVDL","NVDS",
    # Leverage Shares 2x (single-stock)
    "NBIG","MSTX","MSTU","MSTZ","AMZU","AMZD","GOGL","GOGZ",
    # T-Rex 2x
    "CONL","NVDX","MAGX","MAGQ","PLTR2X",
    # MicroSectors
    "BNKU","BNKD","FNGU","FNGD","OILU","OILD","URAU","URAD",
    # Crypto leveraged
    "ETHU","ETHD","BITU","BITX","ETHW","BTCW",
}

# 이름 패턴으로 레버리지 감지 (yfinance shortName 포함)
_LEVERAGED_NAME_PATTERNS = [
    "2x long","2x short","3x long","3x short","ultra pro","ultrashort",
    "leverage shares","granitesha","direxion daily","proshares ultra",
    "bull 2x","bear 2x","bull 3x","bear 3x","daily 2x","daily 3x",
    "1.5x","2x etf","3x etf","inverse daily",
]


def _is_likely_leveraged_by_volatility(df: pd.DataFrame) -> bool:
    """
    Heuristic: 레버리지 ETF는 일간 변동폭이 비정상적으로 큼.
    - 2x ETF 기준: 기초자산이 5% 움직이면 ETF는 10% 이상 변동
    - 정상 고변동 주식(MU, INTC 등)과 구분하기 위해 임계값을 높게 설정
    - 최근 20일 중 10% 초과 일일 변동이 4번 이상 → 레버리지 의심
    """
    if len(df) < 15:
        return False
    daily_ret = df["Close"].pct_change().abs()
    extreme_days = int((daily_ret.tail(20) > 0.10).sum())
    return extreme_days >= 4


# ── helpers ──────────────────────────────────────────────────────────────────

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """RSI with Wilder's smoothing (EMA alpha=1/n)."""
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
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
    std = s.rolling(n).std(ddof=0)  # population std (Bollinger standard)
    upper = mid + 2 * std
    lower = mid - 2 * std
    bw = (upper - lower) / (mid + 1e-9)
    return upper, mid, lower, bw


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series,
           k: int = 14, d: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    pct_k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-9)
    pct_d = _sma(pct_k, d)
    return pct_k, pct_d


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _safe(s: pd.Series, i: int = -1) -> float:
    """Safely get scalar from series, return NaN on error."""
    try:
        v = float(s.iloc[i])
        return v if not np.isnan(v) else 0.0
    except Exception:
        return 0.0


def _series_to_list(s: pd.Series, decimals: int = 2) -> list:
    """Convert series to JSON-safe list, replacing NaN with None."""
    return [round(float(v), decimals) if not np.isnan(v) else None for v in s]


# ── scoring ───────────────────────────────────────────────────────────────────

def score_stock(ticker: str, df: pd.DataFrame) -> Optional[dict]:
    """
    Compute 11-signal score. Returns None if data insufficient.

    Signals returned as boolean dict (keys match SIGNAL_LABELS in reels):
      golden_cross    — MA20 > MA60 (bonus if recent crossover)
      volume_confirm  — recent volume spike ≥ 1.5× 20d avg
      rsi_signal      — RSI 50-70 zone
      rsi_divergence  — bullish RSI divergence (price lower, RSI higher)
      bollinger_break — BB squeeze or upper-band breakout
      macd_cross      — MACD line > signal (bonus if recent crossover)
      stoch_signal    — stochastic recovering from oversold
      ma_alignment    — MA5 > MA20 > MA60 (full bullish stack)
      relative_strength — 20d return > SPY (set in run_screener)
      fib_support     — price within 1.5×ATR of Fib 38.2/50/61.8%

    Chart data in REELS format: {closes, highs, lows, volumes}
    Chart data in SPA format:   {dates, open, high, low, close, volume, ma5, ma20, ...}
    Swing data: ATR-based entry/stop/target with R:R ratio.
    """
    if len(df) < 60:
        return None

    # ── 레버리지 ETF 1차 필터 (블랙리스트 + 변동성 휴리스틱) ──
    if ticker in LEVERAGED_BLACKLIST:
        print(f"[screener] {ticker}: 레버리지 블랙리스트 — 제외")
        return None
    if _is_likely_leveraged_by_volatility(df):
        print(f"[screener] {ticker}: 레버리지 의심 (극단 변동 ≥5회/20일) — 제외")
        return None

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    # Dollar volume filter — $500K/day minimum; avg = prior 20 days (exclude today)
    if len(volume) < 21:
        return None
    avg_vol_20 = float(volume.iloc[-21:-1].mean())
    last_close = float(close.iloc[-1])
    if avg_vol_20 * last_close < 500_000:
        return None

    score    = 0
    signals  = {}   # dict[str, bool] — keys match SIGNAL_LABELS in reels
    details  = {}

    # ── Compute all indicators upfront ──
    ma5      = _sma(close, 5)
    ma20     = _sma(close, 20)
    ma60     = _sma(close, 60)
    rsi_s    = _rsi(close)
    macd_l, macd_sig, macd_hist = _macd(close)
    bb_up, _, bb_lo, bw         = _bollinger(close)
    stk, stk_d = _stoch(high, low, close)
    atr_s    = _atr(high, low, close, 14)

    ma5_v    = _safe(ma5)
    ma20_v   = _safe(ma20)
    ma60_v   = _safe(ma60)
    rsi_v    = _safe(rsi_s)
    ml       = _safe(macd_l)
    ms       = _safe(macd_sig)
    mh       = _safe(macd_hist)
    mh_prev  = _safe(macd_hist, -2)
    bw_v     = _safe(bw)
    bw_20ago = _safe(bw.tail(21).iloc[0:1].squeeze()) if len(bw) >= 21 else bw_v
    bb_up_v  = _safe(bb_up)
    bb_lo_v  = _safe(bb_lo)
    stk_v    = _safe(stk)
    stk_d_v  = _safe(stk_d)
    stk_prev = _safe(stk, -2)
    atr_v    = _safe(atr_s)
    if atr_v <= 0:
        atr_v = last_close * 0.02  # fallback: 2% of price

    vol_ratio     = float(volume.iloc[-1]) / (avg_vol_20 + 1)
    max_vol_5d    = float(volume.tail(5).max()) / (avg_vol_20 + 1)
    effective_vol = max(vol_ratio, max_vol_5d)

    # ── 1. Golden Cross (MA20 > MA60) ──
    is_golden    = ma20_v > ma60_v
    # Detect actual crossover within last 10 bars
    recent_gc    = False
    if len(ma20) >= 11 and len(ma60) >= 11:
        for i in range(-10, -1):
            try:
                prev_a, prev_b = float(ma20.iloc[i - 1]), float(ma60.iloc[i - 1])
                curr_a, curr_b = float(ma20.iloc[i]),     float(ma60.iloc[i])
                if prev_a <= prev_b and curr_a > curr_b:
                    recent_gc = True
                    break
            except Exception:
                pass

    if is_golden:
        score += 12
        if recent_gc:
            score += 5  # fresh crossover bonus
    signals["golden_cross"] = is_golden
    details["golden_cross"]  = is_golden
    details["recent_gc"]     = recent_gc

    # ── 2. Volume surge (today vs prior 20-day avg; effective_vol uses same avg_vol_20) ──
    is_vol_confirmed = effective_vol >= 1.5
    if effective_vol >= 2.5:
        score += 10
    elif effective_vol >= 2.0:
        score += 8
    elif effective_vol >= 1.5:
        score += 6
    elif effective_vol >= 1.2:
        score += 3
    signals["volume_confirm"] = is_vol_confirmed
    details["vol_ratio"]      = round(vol_ratio, 2)
    details["max_vol_5d"]     = round(max_vol_5d, 2)

    # ── 3. RSI momentum ──
    is_rsi_ok = 50 <= rsi_v <= 70
    if 57 <= rsi_v <= 70:
        score += 10
    elif 50 <= rsi_v < 57:
        score += 6
    elif 70 < rsi_v <= 80:
        score += 4
    elif rsi_v > 80:
        score += 1  # overbought
    signals["rsi_signal"] = is_rsi_ok
    details["rsi"]        = round(rsi_v, 1)

    # ── 4. RSI Divergence (bullish: price lower, RSI higher) ──
    rsi_div = False
    if len(close) >= 21 and len(rsi_s) >= 21:
        p_now, p_10 = float(close.iloc[-1]), float(close.iloc[-10])
        r_now, r_10 = float(rsi_s.iloc[-1]), float(rsi_s.iloc[-10])
        if p_now < p_10 and r_now > r_10 and rsi_v < 55:
            rsi_div = True
            score += 6
    signals["rsi_divergence"] = rsi_div

    # ── 5. MACD crossover ──
    is_macd_bull   = ml > ms
    # Detect actual crossover within last 5 bars
    macd_crossed   = False
    if len(macd_l) >= 6:
        for i in range(-5, -1):
            try:
                if (float(macd_l.iloc[i - 1]) <= float(macd_sig.iloc[i - 1]) and
                        float(macd_l.iloc[i]) > float(macd_sig.iloc[i])):
                    macd_crossed = True
                    break
            except Exception:
                pass

    if macd_crossed:
        score += 10
    elif ml > ms and mh > mh_prev and mh > 0:
        score += 8
    elif ml > ms and mh > 0:
        score += 5
    elif ml > ms:
        score += 3
    signals["macd_cross"]       = is_macd_bull
    details["macd"]             = round(ml - ms, 4)
    details["macd_cross_recent"] = macd_crossed

    # ── 6. Bollinger Squeeze + Breakout ──
    bb_ratio     = bw_v / (bw_20ago + 1e-9)
    is_squeeze   = bw_v < bw_20ago * 0.75
    bb_pos       = (last_close - bb_lo_v) / (bb_up_v - bb_lo_v + 1e-9)
    is_bb        = is_squeeze or bb_pos > 0.80

    if is_squeeze:
        score += 8
    elif bw_v < bw_20ago * 0.88:
        score += 4
    if bb_pos > 0.85:
        score += 3  # upper-band breakout bonus
    signals["bollinger_break"] = is_bb
    details["bb_squeeze"]      = round(bb_ratio, 3)
    details["bb_position"]     = round(bb_pos, 3)

    # ── 7. Stochastic recovery ──
    is_stoch = stk_prev < 25 and stk_v > stk_prev and stk_v > stk_d_v
    if is_stoch:
        score += 10
    elif stk_v < 30 and stk_v > stk_prev:
        score += 5
    elif 40 < stk_v < 60 and stk_v > stk_d_v:
        score += 3
    signals["stoch_signal"] = is_stoch
    details["stoch_k"]      = round(stk_v, 1)

    # ── 8. MA Alignment (MA5 > MA20 > MA60) ──
    is_aligned = ma5_v > ma20_v > ma60_v
    if is_aligned:
        score += 8
    elif ma20_v > ma60_v:
        score += 3  # partial alignment
    signals["ma_alignment"] = is_aligned
    details["ma5"]          = round(ma5_v, 2)
    details["ma20"]         = round(ma20_v, 2)
    details["ma60"]         = round(ma60_v, 2)

    # ── 9. 52-week high proximity ──
    hi52 = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
    dist_52w = (hi52 - last_close) / (hi52 + 1e-9)
    if dist_52w <= 0.03:
        score += 10
    elif dist_52w <= 0.10:
        score += 6
    elif dist_52w <= 0.20:
        score += 3
    details["dist_52w"] = round(dist_52w, 4)

    # ── 10. 5-day momentum ──
    ret5 = 0.0
    if len(close) >= 6:
        ret5 = float(close.iloc[-1] / close.iloc[-6] - 1) * 100
        if ret5 >= 8:
            score += 8
        elif ret5 >= 4:
            score += 5
        elif ret5 >= 1.5:
            score += 3
        elif ret5 < -5:
            score -= 3
    details["ret_5d"] = round(ret5, 2)

    # ── 11. 20-day return (RS vs SPY set in run_screener) ──
    ret20 = 0.0
    if len(close) >= 21:
        ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) * 100
    details["ret_20d"] = round(ret20, 2)
    signals["relative_strength"] = False  # filled in by run_screener

    # ── 12. Fibonacci Support ──
    hi60   = float(high.tail(60).max())
    lo60   = float(low.tail(60).min())
    rng60  = hi60 - lo60
    fib382 = hi60 - 0.382 * rng60
    fib500 = hi60 - 0.500 * rng60
    fib618 = hi60 - 0.618 * rng60
    tol    = atr_v * 1.5
    is_fib = any(abs(last_close - f) <= tol for f in [fib382, fib500, fib618])
    if is_fib:
        score += 7
    signals["fib_support"] = is_fib
    details["fib_levels"]  = {
        "h60": round(hi60, 2), "l60": round(lo60, 2),
        "r382": round(fib382, 2), "r500": round(fib500, 2), "r618": round(fib618, 2),
    }

    # ── Swing Data (ATR-based) ──
    entry_low   = round(last_close * 0.995, 2)
    entry_high  = round(last_close * 1.005, 2)
    # Stop: 2.0×ATR or 7% max, whichever is tighter; floor at 60-day low
    stop_dist   = min(2.0 * atr_v, last_close * 0.07)
    stop_loss   = round(max(last_close - stop_dist, lo60 * 0.99), 2)
    stop_pct    = round((stop_loss - last_close) / last_close * 100, 1)
    target1     = round(last_close + 3.0 * atr_v, 2)
    target1_pct = round((target1 - last_close) / last_close * 100, 1)
    target2     = round(last_close + 6.0 * atr_v, 2)
    target2_pct = round((target2 - last_close) / last_close * 100, 1)
    risk        = last_close - stop_loss
    reward      = target2 - last_close
    rr_ratio    = round(reward / risk, 1) if risk > 0.01 else 1.5

    swing = {
        "entry_low":   entry_low,    "entry_high":   entry_high,
        "stop_loss":   stop_loss,    "stop_pct":     stop_pct,
        "target1":     target1,      "target1_pct":  target1_pct,  "target1_week": 2,
        "target2":     target2,      "target2_pct":  target2_pct,  "target2_week": 4,
        "rr_ratio":    rr_ratio,     "vol_multiple": round(effective_vol, 1),
    }

    # ── Chart data (REELS format: closes/highs/lows/volumes) ──
    chart_df   = df.tail(65).copy()
    ch_closes  = [round(float(v), 2) for v in chart_df["Close"]]
    ch_highs   = [round(float(v), 2) for v in chart_df["High"]]
    ch_lows    = [round(float(v), 2) for v in chart_df["Low"]]
    ch_volumes = [int(v) for v in chart_df["Volume"]]

    chart_data = {
        "closes":  ch_closes,
        "highs":   ch_highs,
        "lows":    ch_lows,
        "volumes": ch_volumes,
    }

    # ── Chart data (SPA format: full indicators) ──
    cclose = chart_df["Close"]
    chart = {
        "dates":     [str(d.date()) for d in chart_df.index],
        "open":      [round(float(v), 2) for v in chart_df["Open"]],
        "high":      ch_highs,
        "low":       ch_lows,
        "close":     ch_closes,
        "volume":    ch_volumes,
        "ma5":       _series_to_list(_sma(cclose, 5)),
        "ma20":      _series_to_list(_sma(cclose, 20)),
        "ma60":      _series_to_list(_sma(cclose, 60)),
        "bb_upper":  _series_to_list(_bollinger(cclose)[0]),
        "bb_lower":  _series_to_list(_bollinger(cclose)[2]),
        "rsi":       _series_to_list(_rsi(cclose), 1),
        "macd_hist": _series_to_list(_macd(cclose)[2], 4),
        "stoch_k":   _series_to_list(_stoch(chart_df["High"], chart_df["Low"], cclose)[0], 1),
        "stoch_d":   _series_to_list(_stoch(chart_df["High"], chart_df["Low"], cclose)[1], 1),
        "fib": {
            "h60": round(hi60, 2), "l60": round(lo60, 2),
            "r382": round(fib382, 2), "r500": round(fib500, 2), "r618": round(fib618, 2),
        },
    }

    # 당일 등락률 (전일 종가 대비)
    prev_close  = float(close.iloc[-2]) if len(close) >= 2 else last_close
    change_pct  = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    return {
        "ticker":     ticker,
        "score":      score,
        "signals":    signals,    # dict[str, bool] — reels-compatible
        "details":    details,
        "price":      round(last_close, 2),
        "change_pct": change_pct,
        "vol_ratio":  round(vol_ratio, 2),
        "chart_data": chart_data,  # reels: closes/highs/lows/volumes
        "chart":      chart,       # SPA: full indicator arrays
        "swing":      swing,
        "atr":        round(atr_v, 2),
    }


def run_screener(
    data: dict[str, Optional[pd.DataFrame]],
    spy_20d: float = 0.0,
    top_n: int = 10,
) -> list[dict]:
    """
    Score all fetched stocks, apply RS bonus vs SPY, return top N.
    Sets signals['relative_strength'] based on actual SPY comparison.
    """
    results = []
    for ticker, df in data.items():
        if df is None:
            continue
        try:
            res = score_stock(ticker, df)
        except Exception as e:
            print(f"[screener] {ticker} error: {e}")
            continue
        if res is None:
            continue

        # RS bonus vs SPY
        rs_diff  = res["details"].get("ret_20d", 0.0) - spy_20d
        rs_bonus = 0
        if rs_diff >= 15:
            rs_bonus = 15
            res["signals"]["relative_strength"] = True
        elif rs_diff >= 8:
            rs_bonus = 10
            res["signals"]["relative_strength"] = True
        elif rs_diff >= 3:
            rs_bonus = 6
            res["signals"]["relative_strength"] = True
        elif rs_diff >= 0:
            rs_bonus = 3
            res["signals"]["relative_strength"] = False
        else:
            res["signals"]["relative_strength"] = False

        res["score"]    += rs_bonus
        res["rs_bonus"]  = rs_bonus
        res["rs_diff"]   = round(rs_diff, 2)

        results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:top_n]

    # Print scoring breakdown for top stocks
    for r in top[:3]:
        sig_on = [k for k, v in r.get("signals", {}).items() if v]
        print(f"  {r['ticker']:<6} score={r['score']:3d}  signals={sig_on}")

    return top
