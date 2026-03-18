#!/usr/bin/env python3.11
"""
Standalone data refresh — fetches top NASDAQ stocks, scores them,
writes docs/data.json without needing the full pipeline to work.
"""

import json
import sys
import time
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

ROOT = Path(__file__).parent.parent.parent
DOCS_JSON = ROOT / "docs" / "data.json"

# ── Ticker universe (liquid NASDAQ/NYSE names) ──────────────────────────────
TICKERS = [
    "NVDA","AAPL","MSFT","AMZN","META","GOOGL","TSLA","AVGO","ORCL","AMD",
    "QCOM","MU","NFLX","ADBE","CRM","INTC","PYPL","SHOP","MRVL","AMAT",
    "LRCX","KLAC","SNPS","CDNS","PANW","CRWD","FTNT","ZS","DDOG","SNOW",
    "PLTR","COIN","HOOD","SOFI","RBLX","ABNB","UBER","SPOT","DASH",
    "NIO","BIDU","PDD","JD","BABA","SOUN","IONQ","QBTS","RGTI",
    "SMCI","DELL","NTAP","PSTG","MDB","GTLB","TTD","ZETA","RAMP",
    "ENPH","FSLR","BE","PLUG","ARM","INTU","AMGN","ISRG","VRTX","REGN",
    "MELI","CTAS","CPRT","ROST","FAST","VRSK","IDXX","BIIB",
    "CZR","FANG","LVS","WYNN","MGM","CCL","RCL","NCLH","AAL","UAL","DAL",
    "RIVN","LCID","XPEV","LI","ACHR","JOBY","IREN","CLSK","MARA","RIOT",
    "APP","HOOD","HIMS","TMDX","RXRX","ARQT","ACMR","ONTO","WOLF","FORM",
    "AXON","PODD","TRMB","ANGI","CFLT","SMAR","ZI","BOX","DOCN","HUBS",
    "BILL","PAYC","PCTY","APPN","JAMF","WEX","TOST","MNDY","AI","PATH",
    "GH","RARE","NTRA","ROIV","ALNY","UTHR","NBIX","ARWR","EXAS",
]

# ── Indicator helpers ────────────────────────────────────────────────────────

def _sma(s, n): return s.rolling(n).mean()
def _ema(s, n): return s.ewm(span=n, adjust=False).mean()

def _rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + g / (l + 1e-9))

def _macd(s):
    fast = _ema(s, 12); slow = _ema(s, 26)
    line = fast - slow; sig = _ema(line, 9)
    return line, sig, line - sig

def _boll(s, n=20):
    mid = _sma(s, n); std = s.rolling(n).std(ddof=0)
    return mid + 2*std, mid, mid - 2*std

def _atr(h, l, c, n=14):
    tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _stoch(h, l, c, k=14, d=3):
    lo = l.rolling(k).min(); hi = h.rolling(k).max()
    pct_k = 100*(c-lo)/(hi-lo+1e-9)
    return pct_k.rolling(d).mean(), pct_k.rolling(d).mean().rolling(d).mean()

def _to_list(s, decimals=4):
    return [round(float(v), decimals) if not np.isnan(v) else None for v in s]

# ── Scoring ──────────────────────────────────────────────────────────────────

def score_stock(ticker, df, spy_20d=0.0):
    if df is None or len(df) < 65:
        return None

    # Flatten MultiIndex columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df['Close'].dropna()
    high  = df['High'].dropna()
    low   = df['Low'].dropna()
    vol   = df['Volume'].dropna()

    # Min data
    if len(close) < 65: return None

    # Dollar volume filter
    avg_vol_20 = float(vol.iloc[-21:-1].mean())
    last_close = float(close.iloc[-1])
    if avg_vol_20 * last_close < 500_000: return None

    # Indicators
    ma5  = _sma(close, 5)
    ma20 = _sma(close, 20)
    ma60 = _sma(close, 60)
    rsi  = _rsi(close, 14)
    macd_line, macd_sig, macd_hist = _macd(close)
    bb_u, bb_m, bb_l = _boll(close, 20)
    atr  = _atr(high, low, close, 14)
    stk, std_d = _stoch(high, low, close)

    def v(s):  return float(s.iloc[-1]) if not np.isnan(s.iloc[-1]) else 0.0
    def v2(s): return float(s.iloc[-2]) if len(s)>=2 and not np.isnan(s.iloc[-2]) else 0.0

    last = v(close)
    ma5v = v(ma5); ma20v = v(ma20); ma60v = v(ma60)
    rsiv = v(rsi)
    macd_v  = v(macd_line); macd_sv = v(macd_sig); macd_hv = v(macd_hist)
    macd_hv2 = v2(macd_hist)
    bb_uv = v(bb_u); bb_mv = v(bb_m); bb_lv = v(bb_l)
    atrv  = v(atr)
    stk_v = v(stk); std_dv = v(std_d)
    vol_current  = float(vol.iloc[-1])
    vol_20d_avg  = float(vol.iloc[-21:-1].mean())
    vol_ratio    = vol_current / (vol_20d_avg + 1)
    max_vol_5d   = float(vol.iloc[-5:].max()) / (vol_20d_avg + 1)
    ret_20d      = float((close.iloc[-1]/close.iloc[-21]-1)*100)
    ret_5d       = float((close.iloc[-1]/close.iloc[-5]-1)*100)
    high_52w     = float(high.tail(252).max())
    dist_52w     = (high_52w - last) / (high_52w + 1e-9)

    # Golden cross: MA20 > MA60
    gc = ma20v > ma60v
    # Recent GC: MA5 just crossed MA20 in last 5 bars
    gc_recent = False
    for i in range(-1, -6, -1):
        try:
            if ma5.iloc[i-1] <= ma20.iloc[i-1] and ma5.iloc[i] > ma20.iloc[i]:
                gc_recent = True; break
        except: pass

    signals = {
        'golden_cross':     bool(gc),
        'volume_confirm':   bool(vol_ratio >= 1.5 or max_vol_5d >= 1.5),
        'rsi_signal':       bool(50 <= rsiv <= 70),
        'rsi_divergence':   bool(rsiv > 45 and ret_5d > 0 and rsiv > v2(rsi)),
        'bollinger_break':  bool(last > bb_mv or (bb_uv - bb_lv) < (bb_mv * 0.1)),
        'macd_cross':       bool(macd_v > macd_sv),
        'stoch_signal':     bool(stk_v > 20 and stk_v > std_dv and v2(stk) < 25),
        'ma_alignment':     bool(ma5v > ma20v and ma20v > ma60v),
        'relative_strength':bool(ret_20d > spy_20d),
        'fib_support':      False,  # computed below
    }

    # Fibonacci support
    hi60 = float(high.tail(60).max()); lo60 = float(low.tail(60).min())
    d60  = hi60 - lo60
    fib_levels = [hi60 - d60*0.618, hi60 - d60*0.500, hi60 - d60*0.382, hi60 - d60*0.236]
    signals['fib_support'] = any(abs(last - lv) <= 1.5*atrv for lv in fib_levels)

    # Scoring
    score = 0
    if gc:          score += 12 + (5 if gc_recent else 0)
    if vol_ratio >= 2.5 or max_vol_5d >= 2.5: score += 10
    elif vol_ratio >= 2.0: score += 8
    elif vol_ratio >= 1.5: score += 6
    if 57 <= rsiv <= 70: score += 10
    elif 50 <= rsiv <= 70: score += 6
    if macd_v > macd_sv and macd_hv > macd_hv2: score += 10
    elif macd_v > macd_sv: score += 6
    if signals['ma_alignment']: score += 8
    if signals['fib_support']:  score += 7
    if signals['bollinger_break']: score += 5
    if signals['stoch_signal']:    score += 5
    if ret_20d > spy_20d: score += 3

    # ATR-based swing
    entry_low  = round(last * 0.995, 2)
    entry_high = round(last * 1.005, 2)
    stop_loss  = round(last - 2*atrv, 2)
    stop_pct   = round((stop_loss/last - 1)*100, 1)
    target1    = round(last + 4*atrv, 2)
    t1_pct     = round((target1/last - 1)*100, 1)
    target2    = round(last + 7*atrv, 2)
    t2_pct     = round((target2/last - 1)*100, 1)
    rr_ratio   = round(abs(t1_pct / stop_pct), 1) if stop_pct != 0 else 2.0

    # Chart arrays (last 65 bars)
    N = min(65, len(close))
    idx = close.index[-N:]

    def arr(s, dec=2):
        sub = s.loc[idx] if hasattr(s, 'loc') else s[-N:]
        return [round(float(v), dec) if not np.isnan(v) else None for v in sub]

    chart = {
        'dates':     [str(d)[:10] for d in idx],
        'open':      arr(df['Open'].loc[idx] if hasattr(df['Open'], 'loc') else df['Open'][-N:]),
        'high':      arr(high.loc[idx]),
        'low':       arr(low.loc[idx]),
        'close':     arr(close.loc[idx]),
        'volume':    [int(v) for v in vol.loc[idx]],
        'ma5':       arr(ma5.loc[idx]),
        'ma20':      arr(ma20.loc[idx]),
        'ma60':      arr(ma60.loc[idx]),
        'bb_upper':  arr(bb_u.loc[idx]),
        'bb_lower':  arr(bb_l.loc[idx]),
        'rsi':       arr(rsi.loc[idx], dec=1),
        'macd_hist': arr(macd_hist.loc[idx], dec=4),
        'stoch_k':   arr(stk.loc[idx], dec=1),
        'stoch_d':   arr(std_d.loc[idx], dec=1),
        'fib':       {
            'h60': round(hi60, 2), 'l60': round(lo60, 2),
            'r382': round(hi60 - d60*0.382, 2),
            'r500': round(hi60 - d60*0.500, 2),
            'r618': round(hi60 - d60*0.618, 2),
        },
    }

    # chart_data (reels format)
    chart_data = {
        'closes':  arr(close.loc[idx]),
        'highs':   arr(high.loc[idx]),
        'lows':    arr(low.loc[idx]),
        'volumes': [int(v) for v in vol.loc[idx]],
    }

    return {
        'ticker':    ticker,
        'name':      ticker,
        'sector':    'NASDAQ',
        'price':     round(last, 2),
        'change_pct': round((last / float(close.iloc[-2]) - 1)*100, 2) if len(close)>=2 else 0,
        'score':     score,
        'vol_ratio': round(vol_ratio, 2),
        'atr':       round(atrv, 4),
        'rs_diff':   round(ret_20d - spy_20d, 2),
        'rs_bonus':  3 if ret_20d > spy_20d else 0,
        'signals':   signals,
        'swing': {
            'entry_low':    entry_low,
            'entry_high':   entry_high,
            'stop_loss':    stop_loss,
            'stop_pct':     abs(stop_pct),
            'target1':      target1,
            'target1_pct':  t1_pct,
            'target1_week': '3-4주',
            'target2':      target2,
            'target2_pct':  t2_pct,
            'target2_week': '6-8주',
            'rr_ratio':     rr_ratio,
            'vol_multiple': round(vol_ratio, 1),
        },
        'chart':      chart,
        'chart_data': chart_data,
        'details': {
            'rsi': round(rsiv, 1), 'macd': round(macd_v, 4),
            'macd_cross_recent': bool(macd_v > macd_sv and macd_hv > macd_hv2),
            'golden_cross': bool(gc), 'recent_gc': gc_recent,
            'bb_position': round((last - bb_lv) / (bb_uv - bb_lv + 1e-9), 3),
            'stoch_k': round(stk_v, 1),
            'dist_52w': round(dist_52w, 4),
            'ret_5d': round(ret_5d, 2), 'ret_20d': round(ret_20d, 2),
            'vol_ratio': round(vol_ratio, 2), 'max_vol_5d': round(max_vol_5d, 2),
        },
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    print(f"\n{'='*60}")
    print(f" Refresh docs/data.json  {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}\n")

    # SPY 20d return for RS comparison
    spy_20d = 0.0
    try:
        spy_df = yf.download('SPY', period='60d', interval='1d', auto_adjust=True, progress=False)
        if isinstance(spy_df.columns, pd.MultiIndex):
            spy_df.columns = spy_df.columns.get_level_values(0)
        closes_spy = spy_df['Close'].dropna()
        if len(closes_spy) >= 21:
            spy_20d = round(float((closes_spy.iloc[-1]/closes_spy.iloc[-21]-1)*100), 2)
        print(f"SPY 20d return: {spy_20d:+.2f}%")
    except Exception as e:
        print(f"SPY fetch error: {e}")

    # Download all tickers
    print(f"\nDownloading {len(TICKERS)} tickers...")
    results = []
    failed = 0

    # Batch download
    try:
        raw = yf.download(
            TICKERS,
            period='1y',
            interval='1d',
            auto_adjust=True,
            progress=False,
            group_by='ticker',
            threads=True,
        )
        print("Batch download complete. Scoring...")
        for ticker in TICKERS:
            try:
                if ticker in raw.columns.get_level_values(0):
                    df = raw[ticker].dropna(how='all')
                    res = score_stock(ticker, df, spy_20d)
                    if res:
                        sig_on = [k for k,v in res['signals'].items() if v]
                        results.append(res)
                        print(f"  ✅ {ticker:<8} score={res['score']:3d}  "
                              f"vol={res['vol_ratio']:.1f}x  sigs={len(sig_on)}: {sig_on}")
                    else:
                        failed += 1
            except Exception as e:
                failed += 1
    except Exception as e:
        print(f"Batch failed ({e}), falling back to individual...")
        for ticker in TICKERS:
            try:
                df = yf.download(ticker, period='1y', interval='1d', auto_adjust=True, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                res = score_stock(ticker, df, spy_20d)
                if res:
                    results.append(res)
                    print(f"  ✅ {ticker} score={res['score']}")
                else:
                    failed += 1
                time.sleep(0.1)
            except Exception:
                failed += 1

    print(f"\n{len(results)} stocks scored, {failed} failed/skipped")
    if not results:
        print("ERROR: No results!")
        return 1

    # Sort by score, take top 10
    results.sort(key=lambda x: x['score'], reverse=True)
    top10 = results[:10]

    print(f"\n--- TOP 10 ---")
    for i, s in enumerate(top10):
        sig_on = [k for k,v in s['signals'].items() if v]
        print(f"  #{i+1} {s['ticker']:<8} score={s['score']:3d}  signals({len(sig_on)}): {sig_on}")

    docs_out = {
        'updated_at':   now.strftime('%Y-%m-%d %H:%M KST'),
        'spy_20d':      spy_20d,
        'top100_count': len(results),
        'stocks':       top10,
    }
    DOCS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DOCS_JSON.write_text(json.dumps(docs_out, ensure_ascii=False, indent=2))
    print(f"\n✅ Saved {len(top10)} stocks → {DOCS_JSON}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
