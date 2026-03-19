#!/usr/bin/env python3.11
"""
NASDAQ 전체 스캔 — 보물주식 발굴용

점수 기준 (100점 만점):
    ① 모멘텀 (20일 수익률 vs SPY 초과)          최대 22pt
    ② 골든크로스 전조 (MA5 수렴/조기 돌파) NEW   최대 20pt ★
    ③ 거래량 급증                                최대 13pt
    ④ MACD 전환 (마이너스→플러스)               최대  8pt
    ⑤ RSI 존 (황금구간 / 과매도 반등)            최대  8pt
    ⑥ 피보나치 지지                              최대  8pt
    ⑦ MA 정배열 (후행, 가중치 축소)              최대  8pt
    ⑧ 볼린저 밴드 돌파/중심선 위                 최대  5pt
    ⑨ 52주 신고가 근접 (5% 이내)                최대  4pt
    ⑩ 스토캐스틱 과매도 반등                     최대  4pt

파이프라인 순서:
    백테스트 업데이트 → 시장 레짐 체크 → SPY 수익률 → 섹터 ETF 캐시
    → 유니버스 수집 → 배치 다운로드+점수 → 어닝 필터 → 섹터 보정
    → 레짐 보정 → Top 10 선발 → 저장 → 백테스트 기록
"""

import json
import sys
import time
import warnings
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

warnings.filterwarnings('ignore')

ROOT         = Path(__file__).parent.parent.parent
DOCS_JSON    = ROOT / "docs" / "data.json"
BACKTEST_LOG = ROOT / "logs" / "backtest_log.json"

# ── 상수 ──────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_LEV_PATTERNS = [
    "2x","3x","ultra","ultrashort","bull 2","bear 2","bull 3","bear 3",
    "daily 2","daily 3","leverag","inverse","proshares ultra","direxion",
    "1.5x","2x etf","3x etf","prosha",
]
_LEV_TICKERS = {
    "TQQQ","SQQQ","UPRO","SPXU","SPXL","SPXS","SSO","SDS","QLD","QID",
    "UDOW","SDOW","TECL","TECS","SOXL","SOXS","LABU","LABD","FAS","FAZ",
    "TNA","TZA","NUGT","DUST","JNUG","JDST","NAIL","DFEN","WEBL","WEBS",
    "TSLL","TSLS","NVDL","NVDS","NVDX","NVDD","MSTU","MSTZ","MSTX",
    "TSLG","AMZU","AMZD","GOGL","GOGZ","CONL","FNGU","FNGD","BNKU","BNKD",
    "BITU","BITX","ETHU","ETHD","IBIT","GBTC",
}

# 섹터명(NASDAQ API) → 대표 ETF
SECTOR_ETF_MAP = {
    "Technology":             "XLK",
    "Consumer Discretionary": "XLY",
    "Financials":             "XLF",
    "Finance":                "XLF",
    "Health Care":            "XLV",
    "Healthcare":             "XLV",
    "Energy":                 "XLE",
    "Industrials":            "XLI",
    "Materials":              "XLB",
    "Real Estate":            "XLRE",
    "Utilities":              "XLU",
    "Consumer Staples":       "XLP",
    "Communication Services": "XLC",
    "Telecommunications":     "XLC",
    "Biotechnology":          "XBI",
}


# ── 수정 1: 시장 레짐 ─────────────────────────────────────────────────────────

def get_market_regime() -> dict:
    """
    SPY 200MA + VIX 기반 시장 레짐 판단.
    bull(1.0) / caution(0.75) / bear(0.5) 세 단계.
    """
    try:
        spy_df = yf.download("SPY", period="1y", interval="1d",
                             auto_adjust=True, progress=False)
        if isinstance(spy_df.columns, pd.MultiIndex):
            spy_df.columns = spy_df.columns.get_level_values(0)
        spy_close    = spy_df["Close"].dropna()
        spy_ma200    = float(spy_close.rolling(200).mean().iloc[-1])
        spy_current  = float(spy_close.iloc[-1])
        spy_above    = spy_current > spy_ma200
        spy_ret_20d  = float((spy_close.iloc[-1]/spy_close.iloc[-21]-1)*100) if len(spy_close)>=21 else 0.0

        vix_df = yf.download("^VIX", period="5d", interval="1d", progress=False)
        if isinstance(vix_df.columns, pd.MultiIndex):
            vix_df.columns = vix_df.columns.get_level_values(0)
        vix_current = float(vix_df["Close"].dropna().iloc[-1])

        if vix_current > 30 or not spy_above:
            regime = "bear"
            desc   = f"VIX {vix_current:.1f} / SPY 200MA {'위' if spy_above else '아래'} → 롱 신호 신뢰도 낮음"
        elif vix_current > 20 or spy_ret_20d < -3:
            regime = "caution"
            desc   = f"VIX {vix_current:.1f} / SPY 20일 {spy_ret_20d:+.1f}% → 주의 구간"
        else:
            regime = "bull"
            desc   = f"VIX {vix_current:.1f} / SPY 200MA 위 → 정상 스캔"

        print(f"[레짐] {desc}")
        if regime == "bear":
            print("⚠ 약세장 레짐 — 모든 롱 신호 점수 × 0.5 적용")

        return {
            "regime":          regime,
            "vix":             round(vix_current, 1),
            "spy_above_200ma": spy_above,
            "spy_ret_20d":     round(spy_ret_20d, 2),
            "spy_current":     round(spy_current, 2),
            "spy_ma200":       round(spy_ma200, 2),
            "description":     desc,
        }
    except Exception as e:
        print(f"[레짐 체크 실패] {e}")
        return {
            "regime": "unknown", "vix": 0, "spy_above_200ma": True,
            "spy_ret_20d": 0, "spy_current": 0, "spy_ma200": 0,
            "description": "레짐 데이터 없음",
        }


def apply_regime_filter(candidates: list, regime_info: dict) -> list:
    """레짐별 점수 멀티플라이어 적용."""
    mult_map = {"bull": 1.0, "caution": 0.75, "bear": 0.5, "unknown": 0.8}
    m = mult_map.get(regime_info.get("regime", "unknown"), 0.8)
    for c in candidates:
        c["raw_score"]   = c.get("raw_score", c["score"])
        c["score"]       = round(c["score"] * m, 1)
        c["regime_mult"] = m
    return candidates


# ── 수정 2: 어닝 필터 ─────────────────────────────────────────────────────────

def get_earnings_date(ticker: str):
    """다음 실적 발표일 반환. 없으면 None."""
    try:
        t   = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return None
        if isinstance(cal, pd.DataFrame):
            if cal.empty:
                return None
            for col in cal.columns:
                try:
                    return pd.Timestamp(col).date()
                except Exception:
                    pass
        elif isinstance(cal, dict):
            earn_dates = cal.get("Earnings Date", [])
            if earn_dates:
                d = earn_dates[0]
                try:
                    return pd.Timestamp(d).date()
                except Exception:
                    pass
        return None
    except Exception:
        return None


def is_near_earnings(ticker: str, buffer_days: int = 5) -> bool:
    """실적 발표일이 오늘로부터 buffer_days일 이내면 True."""
    try:
        edate = get_earnings_date(ticker)
        if edate is None:
            return False
        diff = abs((edate - date.today()).days)
        return diff <= buffer_days
    except Exception:
        return False


def filter_near_earnings(candidates: list) -> list:
    """상위 후보 중 실적 발표 5일 이내 종목 제외."""
    filtered = []
    for c in candidates:
        if is_near_earnings(c["ticker"]):
            print(f"  [어닝 제외] {c['ticker']} — 실적 발표 임박")
            continue
        filtered.append(c)
    return filtered


# ── 수정 5: 섹터 모멘텀 ──────────────────────────────────────────────────────

def fetch_sector_returns(spy_20d: float) -> dict:
    """섹터 ETF 20일 수익률 (vs SPY) 사전 캐시."""
    cache: dict = {}
    etfs = list(set(SECTOR_ETF_MAP.values()))
    try:
        raw = yf.download(
            etfs, period="3mo", interval="1d",
            auto_adjust=True, progress=False, group_by="ticker",
        )
        for etf in etfs:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    s = raw[etf]["Close"].dropna()
                else:
                    s = raw["Close"].dropna()
                if len(s) >= 21:
                    ret = float((s.iloc[-1]/s.iloc[-21]-1)*100)
                    cache[etf] = round(ret - spy_20d, 2)
                else:
                    cache[etf] = 0.0
            except Exception:
                cache[etf] = 0.0
    except Exception as e:
        print(f"[섹터 ETF 로드 실패] {e}")
    return cache


def apply_sector_mult(candidates: list, sector_cache: dict, sect_map: dict) -> list:
    """섹터 ETF 수익률 기반 점수 보정."""
    for c in candidates:
        sector  = sect_map.get(c["ticker"], "Unknown")
        etf     = SECTOR_ETF_MAP.get(sector)
        if etf is None:
            c["sector_mult"] = 1.0
            c["sector_ret"]  = None
            continue
        excess = sector_cache.get(etf)
        if excess is None:
            c["sector_mult"] = 1.0
            c["sector_ret"]  = None
            continue
        if   excess >= 5:   mult = 1.15
        elif excess >= 0:   mult = 1.05
        elif excess >= -5:  mult = 0.90
        else:               mult = 0.75
        c["raw_score"]   = c.get("raw_score", c["score"])
        c["score"]       = round(c["score"] * mult, 1)
        c["sector_mult"] = mult
        c["sector_ret"]  = excess
    return candidates


# ── 수정 6: 백테스트 ──────────────────────────────────────────────────────────

def save_scan_record(stocks: list, scan_date: str | None = None) -> None:
    """오늘 선발 종목 기록 (5영업일 후 수익률 추적용)."""
    if scan_date is None:
        scan_date = date.today().isoformat()
    record = {
        "date": scan_date,
        "picks": [
            {
                "ticker":       s["ticker"],
                "score":        s.get("score", 0),
                "price":        s.get("price", 0),
                "result_price": None,
                "return_pct":   None,
            }
            for s in stocks
        ],
    }
    log = []
    if BACKTEST_LOG.exists():
        try:
            with open(BACKTEST_LOG) as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append(record)
    log = log[-90:]   # 최근 90일치만 유지
    BACKTEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BACKTEST_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def update_backtest_results() -> list:
    """7일 이상 지난 레코드의 result_price 채우기."""
    if not BACKTEST_LOG.exists():
        return []
    try:
        with open(BACKTEST_LOG) as f:
            log = json.load(f)
    except Exception:
        return []

    today   = date.today()
    changed = False
    for record in log:
        scan_date = date.fromisoformat(record["date"])
        if (today - scan_date).days < 7:
            continue
        for pick in record["picks"]:
            if pick.get("result_price") is not None:
                continue
            try:
                start = (scan_date + timedelta(days=1)).isoformat()
                end   = (scan_date + timedelta(days=10)).isoformat()
                hist  = yf.download(
                    pick["ticker"], start=start, end=end,
                    interval="1d", progress=False,
                )
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.get_level_values(0)
                closes = hist["Close"].dropna()
                if len(closes) >= 5:
                    result_p = float(closes.iloc[4])
                    pick["result_price"] = result_p
                    entry_p = pick.get("price", 0)
                    if entry_p and entry_p > 0:
                        pick["return_pct"] = round((result_p/entry_p - 1)*100, 2)
                    changed = True
            except Exception as e:
                print(f"  [백테스트 업데이트 실패] {pick.get('ticker','?')}: {e}")

    if changed:
        with open(BACKTEST_LOG, "w") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
    return log


def get_backtest_summary(log: list) -> dict:
    """백테스트 결과 요약."""
    all_returns = [
        pick["return_pct"]
        for record in log
        for pick in record.get("picks", [])
        if pick.get("return_pct") is not None
    ]
    if not all_returns:
        return {"total": 0, "win_rate": None, "avg_return": None,
                "avg_win": None, "max_return": None, "min_return": None}
    wins = [r for r in all_returns if r > 0]
    return {
        "total":      len(all_returns),
        "win_rate":   round(len(wins)/len(all_returns)*100, 1),
        "avg_return": round(sum(all_returns)/len(all_returns), 2),
        "avg_win":    round(sum(wins)/len(wins), 2) if wins else 0,
        "max_return": round(max(all_returns), 2),
        "min_return": round(min(all_returns), 2),
    }


def print_backtest_summary(log: list) -> None:
    summary = get_backtest_summary(log)
    if summary["total"] == 0:
        print("[백테스트] 결과 데이터 없음 (7일 이상 지난 스캔 없음)\n")
        return
    print(f"\n[백테스트 요약]")
    print(f"  총 거래: {summary['total']}건 | 승률: {summary['win_rate']}%")
    print(f"  평균 수익: {summary['avg_return']}% | 최대이익: {summary['max_return']}% | 최대손실: {summary['min_return']}%\n")


# ── 지표 계산 ──────────────────────────────────────────────────────────────────

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
    pk = 100*(c-lo)/(hi-lo+1e-9)
    return pk.rolling(d).mean(), pk.rolling(d).mean().rolling(d).mean()


# ── 수정 3: 골든크로스 ���조 점수 (NEW) ───────────────────────────────────────

def score_pre_golden_cross(
    ma5: pd.Series,
    ma20: pd.Series,
    vol: pd.Series,
) -> tuple[int, str]:
    """
    골든크로스 전조 신호 점수 (최대 20pt).

    단계별 점수:
      막 크로스 (1~5일):       12pt + 거래량보너스(6pt) = 최대 18pt
      gap 0~2% 수렴 임박:     14pt + 거래량보너스(6pt) = 최대 20pt  ← 핵심
      gap 2~5% 수렴 중:        7pt + 거래량보너스(6pt) = 최대 13pt
      그 외:                   0pt
    """
    try:
        m5  = ma5.dropna()
        m20 = ma20.dropna()
        common = m5.index.intersection(m20.index)
        if len(common) < 10:
            return 0, "데이터 부족"
        m5 = m5.loc[common]; m20 = m20.loc[common]

        curr_m5  = float(m5.iloc[-1])
        curr_m20 = float(m20.iloc[-1])

        # 거래량 증가 보너스
        vol_bonus = 0
        if len(vol) >= 25:
            vol_5d  = float(vol.iloc[-5:].mean())
            vol_20d = float(vol.iloc[-25:-5].mean())
            if vol_20d > 0 and vol_5d / vol_20d > 1.3:
                vol_bonus = 6

        # 최근 크로스 발생일 탐지 (최근 8봉)
        cross_days_ago = None
        for i in range(1, min(9, len(m5))):
            if m5.iloc[-i] > m20.iloc[-i] and m5.iloc[-i-1] <= m20.iloc[-i-1]:
                cross_days_ago = i
                break

        if cross_days_ago is not None and cross_days_ago <= 5:
            return min(12 + vol_bonus, 20), f"골든크로스 {cross_days_ago}일 전 발생"

        if curr_m5 < curr_m20:
            gap_pct = (curr_m20 - curr_m5) / curr_m20
            if gap_pct <= 0.02:
                return min(14 + vol_bonus, 20), f"MA5↑ 수렴 임박 (gap {gap_pct*100:.1f}%)"
            elif gap_pct <= 0.05:
                return min(7 + vol_bonus, 20), f"MA5 수렴 중 (gap {gap_pct*100:.1f}%)"

        return 0, "전조 없음"
    except Exception:
        return 0, "계산 오류"


# ── 스코어링 ──────────────────────────────────────────────────────────────────

def score_stock(ticker: str, df: pd.DataFrame, spy_20d: float = 0.0) -> dict | None:
    if df is None or len(df) < 60:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"].dropna()
    high  = df["High"].dropna()
    low   = df["Low"].dropna()
    vol   = df["Volume"].dropna()

    if len(close) < 60:
        return None

    last_close = float(close.iloc[-1])
    if last_close < 2.0:
        return None

    avg_vol_20     = float(vol.iloc[-21:-1].mean())
    avg_dollar_vol = avg_vol_20 * last_close
    if avg_dollar_vol < 1_000_000:
        return None

    # pump 필터: 얇은 유동성 + 폭발적 단기 급등 배제
    ret_20d_pre   = float((close.iloc[-1]/close.iloc[-21]-1)*100) if len(close)>=21 else 0
    vol_ratio_pre = float(vol.iloc[-1]) / (avg_vol_20 + 1)
    if avg_dollar_vol < 5_000_000 and ret_20d_pre > 60 and vol_ratio_pre > 5:
        return None

    # 지표 계산
    ma5          = _sma(close, 5)
    ma20         = _sma(close, 20)
    ma60         = _sma(close, 60)
    rsi          = _rsi(close, 14)
    ml, ms, mh   = _macd(close)
    bb_u, bb_m, bb_l = _boll(close, 20)
    atr          = _atr(high, low, close, 14)
    stk, std_d   = _stoch(high, low, close)

    def v(s):  return float(s.iloc[-1])  if not np.isnan(s.iloc[-1])  else 0.0
    def v2(s): return float(s.iloc[-2])  if len(s)>=2 and not np.isnan(s.iloc[-2]) else 0.0
    def v3(s): return float(s.iloc[-3])  if len(s)>=3 and not np.isnan(s.iloc[-3]) else 0.0

    last   = v(close)
    ma5v   = v(ma5);  ma20v = v(ma20); ma60v = v(ma60)
    rsiv   = v(rsi);  rsi_p = v2(rsi)
    mlv    = v(ml);   msv   = v(ms);   mhv   = v(mh)
    mhv2   = v2(mh);  mhv3  = v3(mh)
    bb_uv  = v(bb_u); bb_mv = v(bb_m); bb_lv = v(bb_l)
    atrv   = v(atr)
    stkv   = v(stk);  stdv  = v(std_d)

    vol_cur     = float(vol.iloc[-1])
    vol_20d_avg = float(vol.iloc[-21:-1].mean())
    vol_ratio   = vol_cur / (vol_20d_avg + 1)
    max_vol_5d  = float(vol.iloc[-5:].max()) / (vol_20d_avg + 1)

    ret_20d  = float((close.iloc[-1]/close.iloc[-21]-1)*100) if len(close)>=21 else 0
    ret_5d   = float((close.iloc[-1]/close.iloc[-5]-1)*100)  if len(close)>=5  else 0
    high_52w = float(high.tail(252).max())
    dist_52w = (high_52w - last) / (high_52w + 1e-9)

    # ── 신호 판단 ─────────────────────────────────────────────────────────────

    gc = ma20v > ma60v
    gc_recent = False
    for i in range(-1, -6, -1):
        try:
            if ma5.iloc[i-1] <= ma20.iloc[i-1] and ma5.iloc[i] > ma20.iloc[i]:
                gc_recent = True; break
        except Exception:
            pass

    early_cross = ma5v > ma20v

    macd_turned = False
    for i in range(-1, -11, -1):
        try:
            if ml.iloc[i-1] <= 0 and ml.iloc[i] > 0:
                macd_turned = True; break
        except Exception:
            pass

    rsi_oversold_recovery = False
    if rsiv > 45:
        rsi_arr = rsi.dropna()
        if len(rsi_arr) >= 15 and (rsi_arr.iloc[-15:] < 35).any():
            rsi_oversold_recovery = True

    hi60 = float(high.tail(60).max()); lo60 = float(low.tail(60).min())
    d60  = hi60 - lo60
    fib_levels  = [hi60-d60*0.618, hi60-d60*0.500, hi60-d60*0.382, hi60-d60*0.236]
    fib_support = any(abs(last - lv) <= 1.5*atrv for lv in fib_levels)

    signals = {
        "golden_cross":      bool(gc),
        "early_trend":       bool(early_cross and not gc),
        "volume_confirm":    bool(vol_ratio >= 1.5 or max_vol_5d >= 1.5),
        "rsi_signal":        bool(50 <= rsiv <= 73),
        "rsi_divergence":    bool(rsiv > 45 and ret_5d > 0 and rsiv > rsi_p),
        "rsi_oversold":      bool(rsi_oversold_recovery),
        "bollinger_break":   bool(last > bb_mv),
        "macd_cross":        bool(mlv > msv),
        "macd_turned":       bool(macd_turned),
        "stoch_signal":      bool(stkv > 20 and stkv > stdv and v2(stk) < 30),
        "ma_alignment":      bool(ma5v > ma20v and ma20v > ma60v),
        "relative_strength": bool(ret_20d > spy_20d),
        "fib_support":       bool(fib_support),
    }

    # ── 점수 계산 (100점 만점) ────────────────────────────────────────────────

    score = 0

    # ① 모멘텀 (SPY 대비 초과, 22pt max)
    rs_excess = ret_20d - spy_20d
    if   rs_excess >= 50: score += 22
    elif rs_excess >= 35: score += 18
    elif rs_excess >= 25: score += 15
    elif rs_excess >= 15: score += 11
    elif rs_excess >= 8:  score += 7
    elif rs_excess >= 3:  score += 4
    elif rs_excess > 0:   score += 2

    # ② 골든크로스 전조 (20pt max) ★ NEW
    pre_gc_score, pre_gc_note = score_pre_golden_cross(ma5, ma20, vol)
    score += pre_gc_score

    # ③ 거래량 (13pt max)
    if   max_vol_5d >= 3.0: score += 13
    elif max_vol_5d >= 2.0: score += 10
    elif vol_ratio  >= 2.0: score += 9
    elif vol_ratio  >= 1.5: score += 6
    elif vol_ratio  >= 1.2: score += 2

    # ④ MACD (8pt max)
    if   macd_turned:                                    score += 8
    elif mlv > msv and mhv > mhv2 and mhv2 > mhv3:     score += 7
    elif mlv > msv and mhv > mhv2:                      score += 5
    elif mlv > msv:                                      score += 3

    # ⑤ RSI (8pt max)
    if   rsi_oversold_recovery: score += 8
    elif 55 <= rsiv <= 70:      score += 8
    elif 50 <= rsiv <= 73:      score += 5
    elif rsiv > 73:             score += 3

    # ⑥ 피보나치 지지 (8pt)
    if fib_support:             score += 8

    # ⑦ MA 정배열 (후행, 8pt max — 기존 17pt에서 대폭 축소)
    if signals["ma_alignment"]:  score += 8
    elif gc:                     score += 5
    elif signals["early_trend"]: score += 3

    # ⑧ 볼린저 (5pt max)
    if   last > bb_uv: score += 5
    elif last > bb_mv: score += 3

    # ⑨ 52주 신고가 근접 (4pt)
    if dist_52w <= 0.05: score += 4

    # ⑩ 스토캐스틱 (4pt — 기존 3pt에서 증가)
    if signals["stoch_signal"]: score += 4

    # ATR 기반 스윙 트레이드 목표
    entry_low  = round(last * 0.995, 2)
    entry_high = round(last * 1.005, 2)
    stop_loss  = round(last - 2*atrv, 2)
    stop_pct   = round((stop_loss/last - 1)*100, 1)
    target1    = round(last + 3.5*atrv, 2)
    t1_pct     = round((target1/last - 1)*100, 1)
    target2    = round(last + 6*atrv, 2)
    t2_pct     = round((target2/last - 1)*100, 1)
    rr_ratio   = round(abs(t1_pct / stop_pct), 1) if stop_pct != 0 else 2.0

    # 차트 배열 (최근 65봉)
    N   = min(65, len(close))
    idx = close.index[-N:]

    def arr(s, dec=2):
        sub = s.loc[idx] if hasattr(s, "loc") else s[-N:]
        return [round(float(x), dec) if not np.isnan(x) else None for x in sub]

    chart = {
        "dates":     [str(d)[:10] for d in idx],
        "open":      arr(df["Open"].loc[idx]),
        "high":      arr(high.loc[idx]),
        "low":       arr(low.loc[idx]),
        "close":     arr(close.loc[idx]),
        "volume":    [int(x) for x in vol.loc[idx]],
        "ma5":       arr(ma5.loc[idx]),
        "ma20":      arr(ma20.loc[idx]),
        "ma60":      arr(ma60.loc[idx]),
        "bb_upper":  arr(bb_u.loc[idx]),
        "bb_lower":  arr(bb_l.loc[idx]),
        "rsi":       arr(rsi.loc[idx], dec=1),
        "macd_hist": arr(mh.loc[idx], dec=4),
        "stoch_k":   arr(stk.loc[idx], dec=1),
        "stoch_d":   arr(std_d.loc[idx], dec=1),
        "fib": {
            "h60":  round(hi60, 2), "l60": round(lo60, 2),
            "r236": round(hi60-d60*0.236, 2),
            "r382": round(hi60-d60*0.382, 2),
            "r500": round(hi60-d60*0.500, 2),
            "r618": round(hi60-d60*0.618, 2),
        },
    }

    return {
        "ticker":       ticker,
        "name":         ticker,
        "sector":       "NASDAQ",
        "price":        round(last, 2),
        "change_pct":   round((last/float(close.iloc[-2])-1)*100, 2) if len(close)>=2 else 0,
        "score":        score,
        "raw_score":    score,   # 레짐/섹터 보정 전 원점수
        "regime_mult":  1.0,
        "sector_mult":  1.0,
        "sector_ret":   None,
        "pre_gc_score": pre_gc_score,
        "pre_gc_note":  pre_gc_note,
        "vol_ratio":    round(vol_ratio, 2),
        "atr":          round(atrv, 4),
        "rs_diff":      round(rs_excess, 2),
        "signals":      signals,
        "swing": {
            "entry_low":    entry_low,
            "entry_high":   entry_high,
            "stop_loss":    stop_loss,
            "stop_pct":     abs(stop_pct),
            "target1":      target1,
            "target1_pct":  t1_pct,
            "target1_week": "3-4주",
            "target2":      target2,
            "target2_pct":  t2_pct,
            "target2_week": "6-8주",
            "rr_ratio":     rr_ratio,
            "vol_multiple": round(vol_ratio, 1),
        },
        "chart":      chart,
        "chart_data": {
            "closes":  arr(close.loc[idx]),
            "highs":   arr(high.loc[idx]),
            "lows":    arr(low.loc[idx]),
            "volumes": [int(x) for x in vol.loc[idx]],
        },
        "details": {
            "rsi":              round(rsiv, 1),
            "macd":             round(mlv, 4),
            "macd_cross_recent":bool(macd_turned),
            "golden_cross":     bool(gc),
            "recent_gc":        gc_recent,
            "bb_position":      round((last-bb_lv)/(bb_uv-bb_lv+1e-9), 3),
            "stoch_k":          round(stkv, 1),
            "dist_52w":         round(dist_52w, 4),
            "ret_5d":           round(ret_5d, 2),
            "ret_20d":          round(ret_20d, 2),
            "vol_ratio":        round(vol_ratio, 2),
            "max_vol_5d":       round(max_vol_5d, 2),
        },
    }


# ── 유니버스 수집 ─────────────────────────────────────────────────────────────

def parse_mktcap(s) -> float:
    s = str(s).strip().lstrip("$").upper().replace(",", "")
    if not s or s in ("N/A", "-", ""):
        return 0.0
    try:
        if "T" in s: return float(s.replace("T", "")) * 1e12
        if "B" in s: return float(s.replace("B", "")) * 1e9
        if "M" in s: return float(s.replace("M", "")) * 1e6
        if "K" in s: return float(s.replace("K", "")) * 1e3
        return float(s)
    except Exception:
        return 0.0


def fetch_nasdaq_tickers() -> list[dict]:
    tickers: list[dict] = []
    seen: set[str] = set()

    for exchange in ["NASDAQ", "NYSE"]:
        try:
            url = (f"https://api.nasdaq.com/api/screener/stocks"
                   f"?tableonly=true&limit=10000&exchange={exchange}&download=true")
            r    = requests.get(url, headers=HEADERS, timeout=25)
            rows = r.json()["data"]["rows"]
            for row in rows:
                sym    = str(row.get("symbol","")).strip().upper()
                name   = str(row.get("name","")).strip()
                sec    = str(row.get("sector","Unknown")).strip() or "Unknown"
                mktcap = parse_mktcap(row.get("marketCap", 0))
                if sym and sym not in seen and sym.isalpha() and len(sym) <= 5:
                    seen.add(sym)
                    tickers.append({"ticker": sym, "name": name, "sector": sec, "market_cap": mktcap})
            print(f"  {exchange}: {len(tickers)} 누계")
        except Exception as e:
            print(f"  {exchange} API 실패: {e}")

    if len(tickers) >= 500:
        return tickers

    # S&P500 Wikipedia fallback
    try:
        df = pd.read_html(requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=15
        ).text)[0]
        for _, row in df.iterrows():
            sym  = str(row.get("Symbol","")).replace(".", "-").strip().upper()
            name = str(row.get("Security",""))
            sec  = str(row.get("GICS Sector","Unknown"))
            if sym and sym not in seen:
                seen.add(sym)
                tickers.append({"ticker": sym, "name": name, "sector": sec, "market_cap": 0})
        print(f"  S&P500 fallback: {len(tickers)} 누계")
    except Exception as e:
        print(f"  S&P500 실패: {e}")

    FALLBACK = [
        "NVDA","AAPL","MSFT","AMZN","META","GOOGL","TSLA","AVGO","ORCL","AMD",
        "QCOM","MU","NFLX","ADBE","CRM","INTC","PYPL","SHOP","MRVL","AMAT",
        "LRCX","KLAC","SNPS","CDNS","PANW","CRWD","FTNT","ZS","DDOG","SNOW",
        "PLTR","ARM","INTU","SMCI","DELL","NTAP","PSTG","TTD","APP","NET",
        "COIN","HOOD","MSTR","MARA","RIOT","CLSK","IREN","CIFR","BTBT","HUT",
        "SOFI","AFRM","UPST","LC","MQ","DAVE","BILL","PAYC","TOST",
        "SOUN","PATH","AI","BBAI","IONQ","QBTS","RGTI","QUBT",
        "ASTS","RKLB","LUNR","SPCE","IRDM",
        "CRCL","RDDT","RBRK","MNDY","HIMS","RXRX","DOCN","CFLT","GTLB","DKNG",
        "DUOL","CELH","ONON","DECK","LULU","CROX","BOOT",
        "ONTO","WOLF","ACMR","FORM","AEHR","MPWR","SWKS","MCHP","ADI","TXN",
        "NXPI","ENTG","MKSI","AZTA","SITM",
        "UTHR","ROIV","EXAS","RARE","NTRA","ALNY","NBIX","VRTX","REGN","AMGN",
        "ISRG","IDXX","PODD","HALO","TMDX","ARWR","GH","CELC","INVA","NVCR",
        "PCVX","RVMD","CORT","FOLD","HRMY","PRAX",
        "NIO","BIDU","PDD","JD","BABA","XPEV","LI","TCOM","MNSO",
        "ENPH","FSLR","BE","PLUG","ARRY","NOVA","HASI","SHLS",
        "MDB","HUBS","BOX","PCTY","APPN","JAMF","WEX","ZETA","RAMP","SMAR",
        "ABNB","UBER","DASH","LYFT","SPOT","RBLX","DUOL","PTON",
        "CZR","MGM","LVS","WYNN","RCL","CCL","NCLH","AAL","UAL","DAL",
        "RIVN","LCID","ACHR","JOBY",
        "AXON","VRSK","FAST","ROST","CPRT","CTAS","MELI","FANG",
    ]
    for sym in FALLBACK:
        if sym not in seen:
            seen.add(sym)
            tickers.append({"ticker": sym, "name": sym, "sector": "NASDAQ", "market_cap": 0})
    print(f"  Fallback 적용 후: {len(tickers)} 누계")
    return tickers


def is_leveraged(ticker: str, name: str = "") -> bool:
    if ticker in _LEV_TICKERS:
        return True
    nm = name.lower()
    return any(p in nm for p in _LEV_PATTERNS)


# ── 수정 8: Main 파이프라인 재정렬 ───────────────────────────────────────────

def main():
    t_start  = time.time()
    KST      = timezone(timedelta(hours=9))
    ET       = pytz.timezone("America/New_York")
    now_kst  = datetime.now(KST)
    now_et   = datetime.now(ET)

    print(f"\n{'='*65}")
    print(f" NASDAQ 전체 보물주 스캔  {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*65}\n")

    # 수정 3: 스캔 품질 판단 (장중 여부)
    hour_et = now_et.hour
    if 9 <= hour_et < 16:
        scan_quality = {
            "quality": "intraday",
            "note": "장중 스캔 — 종가 미확정, 신호 신뢰도 낮음",
            "reliability": 0.75,
        }
    elif 16 <= hour_et < 20:
        scan_quality = {
            "quality": "afterhours",
            "note": "장 마감 직후 — 종가 확정, 신뢰도 높음",
            "reliability": 1.0,
        }
    else:
        scan_quality = {
            "quality": "overnight",
            "note": "프리마켓/야간 — 전일 종가 기준, 신뢰도 높음",
            "reliability": 1.0,
        }
    scan_quality["scanned_at"] = now_et.strftime("%Y-%m-%d %H:%M ET")
    print(f"[스캔 품질] {scan_quality['note']}\n")

    # ── Step 1: 이전 백테스트 결과 업데이트
    print("이전 백테스트 결과 업데이트 중...")
    log = update_backtest_results()
    print_backtest_summary(log)

    # ── Step 2: 시장 레짐 체크 (수정 1)
    print("시장 레짐 체크 중...")
    regime_info = get_market_regime()
    print()

    # ── Step 3: SPY 20일 수익률 (레짐과 별도로 배치 스캔용)
    spy_20d = regime_info.get("spy_ret_20d", 0.0)
    print(f"SPY 20일 수익률: {spy_20d:+.2f}%\n")

    # ── Step 4: 섹터 ETF 수익률 캐시 (수정 5)
    print("섹터 ETF 수익률 로드 중...")
    sector_cache = fetch_sector_returns(spy_20d)
    print(f"  {len(sector_cache)}개 섹터 ETF 로드 완료\n")

    # ── Step 5: 종목 유니버스 수집
    print("NASDAQ/NYSE 전종목 수집 중...")
    universe = fetch_nasdaq_tickers()
    universe = [u for u in universe if not is_leveraged(u["ticker"], u.get("name",""))]
    MIN_MKTCAP = 300_000_000
    universe = [
        u for u in universe
        if u.get("market_cap", 0) == 0 or u["market_cap"] >= MIN_MKTCAP
    ]
    tickers  = [u["ticker"] for u in universe]
    name_map = {u["ticker"]: u.get("name", u["ticker"]) for u in universe}
    sect_map = {u["ticker"]: u.get("sector", "NASDAQ")  for u in universe}
    print(f"유효 종목: {len(tickers)}개 (레버리지·초소형주 제외)\n")

    # ── Step 6: 배치 다운로드 + 점수 계산
    print("OHLCV 배치 다운로드...")
    all_results: list[dict] = []
    BATCH  = 50
    failed = 0

    for start in range(0, len(tickers), BATCH):
        batch       = tickers[start:start+BATCH]
        batch_num   = start//BATCH + 1
        total_batches = (len(tickers)+BATCH-1)//BATCH
        sys.stdout.write(f"\r  배치 {batch_num}/{total_batches} 처리 중 ... (통과: {len(all_results)})  ")
        sys.stdout.flush()
        try:
            raw = yf.download(
                batch, period="1y", interval="1d",
                auto_adjust=True, progress=False,
                group_by="ticker", threads=True,
            )
            for ticker in batch:
                try:
                    if len(batch) == 1:
                        df = raw
                    elif ticker in raw.columns.get_level_values(0):
                        df = raw[ticker].dropna(how="all")
                    else:
                        failed += 1; continue
                    res = score_stock(ticker, df, spy_20d)
                    if res:
                        res["name"]   = name_map.get(ticker, ticker)
                        res["sector"] = sect_map.get(ticker, "NASDAQ")
                        all_results.append(res)
                except Exception:
                    failed += 1
        except Exception:
            for ticker in batch:
                try:
                    df = yf.download(ticker, period="1y", interval="1d",
                                     auto_adjust=True, progress=False)
                    res = score_stock(ticker, df, spy_20d)
                    if res:
                        res["name"]   = name_map.get(ticker, ticker)
                        res["sector"] = sect_map.get(ticker, "NASDAQ")
                        all_results.append(res)
                    time.sleep(0.05)
                except Exception:
                    failed += 1
        time.sleep(0.2)

    print(f"\n\n총 {len(all_results)}개 통과 | {failed}개 실패/제외")

    if not all_results:
        print("ERROR: 결과 없음")
        return 1

    # ── Step 7: 상위 100개 추출
    all_results.sort(key=lambda x: x["score"], reverse=True)
    top100 = all_results[:100]

    # ── Step 8: 어닝 필터 (수정 2, 상위 100개에만)
    print("\n어닝 필터 적용 중 (상위 100개)...")
    top100_filtered = filter_near_earnings(top100)

    # ── Step 9: 섹터 모멘텀 보정 (수정 5)
    top100_sectored = apply_sector_mult(top100_filtered, sector_cache, sect_map)

    # ── Step 10: 레짐 보정 (수정 1)
    top100_regimed = apply_regime_filter(top100_sectored, regime_info)

    # ── Step 11: 최종 Top 10
    top10 = sorted(top100_regimed, key=lambda x: x["score"], reverse=True)[:10]

    # 로그 출력
    print(f"\n{'='*65}")
    print(f" 최종 TOP 10  레짐={regime_info.get('regime','?')} | VIX={regime_info.get('vix',0):.1f} | SPY {spy_20d:+.2f}%")
    print(f"{'='*65}")
    for i, s in enumerate(top10):
        sigs = s.get("signals", {})
        on   = [k for k,v in sigs.items() if v]
        det  = s.get("details", {})
        print(f" #{i+1:2d} {s['ticker']:<8} raw={s.get('raw_score',0):3.0f}→adj={s['score']:4.1f}  "
              f"${s['price']:>8.2f}  RSI={det.get('rsi',0):.0f}  "
              f"20d={det.get('ret_20d',0):+.1f}%  vol={s['vol_ratio']:.1f}x  "
              f"pre_gc={s.get('pre_gc_score',0)}pt")
        print(f"      신호({len(on)}): {on}")
    print(f"{'='*65}")

    elapsed = round(time.time() - t_start, 1)
    print(f"\n⏱ 실행 시간: {elapsed}초\n")

    # ── Step 12: data.json 저장 (수정 7)
    bt_summary = get_backtest_summary(log)
    docs_out = {
        "updated_at":   now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "spy_20d":      spy_20d,
        "top100_count": len(all_results),
        "regime":       regime_info,
        "scan_info":    scan_quality,
        "backtest":     bt_summary,
        "stocks":       top10,
    }
    DOCS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DOCS_JSON.write_text(json.dumps(docs_out, ensure_ascii=False, indent=2))
    print(f"✅ 저장 완료 → {DOCS_JSON}")

    # ── Step 13: 오늘 선발 기록 저장 (수정 6)
    save_scan_record(top10)
    print("✅ 백테스트 기록 저장 완료")

    return 0


if __name__ == "__main__":
    sys.exit(main())
