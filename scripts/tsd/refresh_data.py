#!/usr/bin/env python3.11
"""
NASDAQ 전체 스캔 — 보물주식 발굴용
- NASDAQ API로 전체 종목 리스트 수집 (3000+ 종목)
- 배치 다운로드 후 확장된 스코어링
- 점수 기준:
    ① 모멘텀 (20일 수익률 vs SPY 초과)   최대 20pt
    ② 조기 추세 전환 (MA5>MA20, early reversal)  최대 15pt
    ③ MACD 전환 (마이너스→플러스, 히스토그램 가속)  최대 15pt
    ④ 거래량 급증                          최대 10pt
    ⑤ RSI 존 (50-70 또는 과매도 반등)      최대 10pt
    ⑥ 골든크로스 (MA20>MA60)             최대 10pt (가중치 낮춤)
    ⑦ 피보나치 지지                        최대 7pt
    ⑧ 볼린저 밴드 돌파/수축               최대 5pt
    ⑨ 상대강도 (SPY 대비)                 최대 5pt
    ⑩ 스토캐스틱 반등                     최대 3pt
"""

import json
import sys
import time
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings('ignore')

ROOT      = Path(__file__).parent.parent.parent
DOCS_JSON = ROOT / "docs" / "data.json"

# ── NASDAQ 전종목 수집 ────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# 알려진 레버리지/인버스 ETF 블랙리스트 패턴
_LEV_PATTERNS = ["2x","3x","ultra","ultrashort","bull 2","bear 2","bull 3","bear 3",
                  "daily 2","daily 3","leverag","inverse","proshares ultra","direxion",
                  "1.5x","2x etf","3x etf","prosha"]
_LEV_TICKERS = {"TQQQ","SQQQ","UPRO","SPXU","SPXL","SPXS","SSO","SDS","QLD","QID",
                 "UDOW","SDOW","TECL","TECS","SOXL","SOXS","LABU","LABD","FAS","FAZ",
                 "TNA","TZA","NUGT","DUST","JNUG","JDST","NAIL","DFEN","WEBL","WEBS",
                 "TSLL","TSLS","NVDL","NVDS","NVDX","NVDD","MSTU","MSTZ","MSTX",
                 "TSLG","AMZU","AMZD","GOGL","GOGZ","CONL","FNGU","FNGD","BNKU","BNKD",
                 "BITU","BITX","ETHU","ETHD","IBIT","GBTC"}


def fetch_nasdaq_tickers() -> list[dict]:
    """NASDAQ 공식 API + NYSE로 전 종목 수집. 실패시 확장 fallback 목록."""
    tickers: list[dict] = []
    seen: set[str] = set()

    for exchange in ["NASDAQ", "NYSE"]:
        try:
            url = (f"https://api.nasdaq.com/api/screener/stocks"
                   f"?tableonly=true&limit=10000&exchange={exchange}&download=true")
            r = requests.get(url, headers=HEADERS, timeout=25)
            rows = r.json()["data"]["rows"]
            for row in rows:
                sym  = str(row.get("symbol","")).strip().upper()
                name = str(row.get("name","")).strip()
                sec  = str(row.get("sector","Unknown")).strip() or "Unknown"
                if sym and sym not in seen and sym.isalpha() and len(sym) <= 5:
                    seen.add(sym)
                    tickers.append({"ticker": sym, "name": name, "sector": sec})
            print(f"  {exchange}: {len(tickers)} 누계")
        except Exception as e:
            print(f"  {exchange} API 실패: {e}")

    if len(tickers) >= 500:
        return tickers

    # Fallback — S&P500 Wikipedia
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
                tickers.append({"ticker": sym, "name": name, "sector": sec})
        print(f"  S&P500 fallback: {len(tickers)} 누계")
    except Exception as e:
        print(f"  S&P500 실패: {e}")

    # 최종 Fallback — 하드코딩 (필수 종목)
    FALLBACK = [
        "NVDA","AAPL","MSFT","AMZN","META","GOOGL","TSLA","AVGO","ORCL","AMD",
        "QCOM","MU","NFLX","ADBE","CRM","INTC","PYPL","SHOP","MRVL","AMAT",
        "LRCX","KLAC","SNPS","CDNS","PANW","CRWD","FTNT","ZS","DDOG","SNOW",
        "PLTR","ARM","INTU","SMCI","DELL","NTAP","PSTG","TTD","APP","NET",
        # 암호화폐/핀테크
        "COIN","HOOD","MSTR","MARA","RIOT","CLSK","IREN","CIFR","BTBT","HUT",
        "SOFI","AFRM","UPST","LC","MQ","DAVE","BILL","PAYC","TOST",
        # AI/양자
        "SOUN","PATH","AI","BBAI","IONQ","QBTS","RGTI","QUBT",
        # 우주/위성
        "ASTS","RKLB","LUNR","SPCE","IRDM",
        # 신규 성장
        "CRCL","RDDT","RBRK","MNDY","HIMS","RXRX","DOCN","CFLT","GTLB","DKNG",
        "DUOL","CELH","ONON","DECK","LULU","CROX","BOOT",
        # 반도체
        "ONTO","WOLF","ACMR","FORM","AEHR","MPWR","SWKS","MCHP","ADI","TXN",
        "NXPI","ENTG","MKSI","AZTA","SITM",
        # 헬스케어
        "UTHR","ROIV","EXAS","RARE","NTRA","ALNY","NBIX","VRTX","REGN","AMGN",
        "ISRG","IDXX","PODD","HALO","TMDX","ARWR","GH","CELC","INVA","NVCR",
        "PCVX","RVMD","CORT","FOLD","HRMY","PRAX",
        # 중국 ADR
        "NIO","BIDU","PDD","JD","BABA","XPEV","LI","TCOM","MNSO",
        # 클린테크
        "ENPH","FSLR","BE","PLUG","ARRY","NOVA","HASI","SHLS",
        # SaaS/클라우드
        "MDB","ZS","HUBS","BOX","PCTY","PAYC","APPN","JAMF","WEX","MNDY",
        "ZETA","RAMP","BILL","DOCN","TOST","SMAR","CFLT",
        # 소비재/여행
        "ABNB","UBER","DASH","LYFT","SPOT","RBLX","RDDT","DUOL","PTON",
        "CZR","MGM","LVS","WYNN","RCL","CCL","NCLH","AAL","UAL","DAL",
        # EV
        "RIVN","LCID","XPEV","LI","ACHR","JOBY",
        # 기타
        "AXON","VRSK","FAST","ROST","CPRT","CTAS","MELI","FANG",
    ]
    for sym in FALLBACK:
        if sym not in seen:
            seen.add(sym)
            tickers.append({"ticker": sym, "name": sym, "sector": "NASDAQ"})
    print(f"  Fallback 적용 후: {len(tickers)} 누계")
    return tickers


def is_leveraged(ticker: str, name: str = "") -> bool:
    if ticker in _LEV_TICKERS:
        return True
    nm = name.lower()
    return any(p in nm for p in _LEV_PATTERNS)


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


# ── 스코어링 ──────────────────────────────────────────────────────────────────

def score_stock(ticker: str, df: pd.DataFrame, spy_20d: float = 0.0) -> dict | None:
    if df is None or len(df) < 60:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close  = df["Close"].dropna()
    high   = df["High"].dropna()
    low    = df["Low"].dropna()
    vol    = df["Volume"].dropna()

    if len(close) < 60:
        return None

    # 최소 가격 필터: $2 이상 (페니스톡 제외)
    last_close = float(close.iloc[-1])
    if last_close < 2.0:
        return None

    # 달러 거래대금 필터 — $1M/일 이상 (적당한 유동성 확보)
    avg_vol_20 = float(vol.iloc[-21:-1].mean())
    if avg_vol_20 * last_close < 1_000_000:
        return None

    # 지표
    ma5   = _sma(close, 5)
    ma20  = _sma(close, 20)
    ma60  = _sma(close, 60)
    rsi   = _rsi(close, 14)
    ml, ms, mh = _macd(close)
    bb_u, bb_m, bb_l = _boll(close, 20)
    atr   = _atr(high, low, close, 14)
    stk, std_d = _stoch(high, low, close)

    def v(s):  return float(s.iloc[-1])  if not (np.isnan(s.iloc[-1]))  else 0.0
    def v2(s): return float(s.iloc[-2])  if len(s)>=2 and not np.isnan(s.iloc[-2]) else 0.0
    def v3(s): return float(s.iloc[-3])  if len(s)>=3 and not np.isnan(s.iloc[-3]) else 0.0

    last   = v(close)
    ma5v   = v(ma5);  ma20v = v(ma20); ma60v = v(ma60)
    rsiv   = v(rsi)
    rsi_p  = v2(rsi)
    mlv    = v(ml);   msv   = v(ms);   mhv   = v(mh)
    mhv2   = v2(mh);  mhv3  = v3(mh)
    bb_uv  = v(bb_u); bb_mv = v(bb_m); bb_lv = v(bb_l)
    atrv   = v(atr)
    stkv   = v(stk);  stdv  = v(std_d)

    vol_cur     = float(vol.iloc[-1])
    vol_20d_avg = float(vol.iloc[-21:-1].mean())
    vol_ratio   = vol_cur / (vol_20d_avg + 1)
    max_vol_5d  = float(vol.iloc[-5:].max()) / (vol_20d_avg + 1)

    ret_20d = float((close.iloc[-1]/close.iloc[-21]-1)*100) if len(close)>=21 else 0
    ret_5d  = float((close.iloc[-1]/close.iloc[-5]-1)*100)  if len(close)>=5  else 0
    ret_3d  = float((close.iloc[-1]/close.iloc[-3]-1)*100)  if len(close)>=3  else 0
    high_52w = float(high.tail(252).max())
    dist_52w = (high_52w - last) / (high_52w + 1e-9)

    # ── 신호 판단 (10개) ──────────────────────────────────────────────────────

    # 골든크로스: MA20 > MA60 (전통적)
    gc = ma20v > ma60v
    gc_recent = False
    for i in range(-1, -6, -1):
        try:
            if ma5.iloc[i-1] <= ma20.iloc[i-1] and ma5.iloc[i] > ma20.iloc[i]:
                gc_recent = True; break
        except: pass

    # 조기 추세 전환: MA5 > MA20 (설령 MA20 < MA60이어도)
    early_cross = ma5v > ma20v

    # MACD 전환: 마이너스→플러스 최근 10봉 이내
    macd_turned = False
    for i in range(-1, -11, -1):
        try:
            if ml.iloc[i-1] <= 0 and ml.iloc[i] > 0:
                macd_turned = True; break
        except: pass

    # RSI 과매도 반등: 최근 15봉 내 RSI < 35 존재 AND 현재 > 45
    rsi_oversold_recovery = False
    if rsiv > 45:
        rsi_arr = rsi.dropna()
        if len(rsi_arr) >= 15:
            if (rsi_arr.iloc[-15:] < 35).any():
                rsi_oversold_recovery = True

    signals = {
        "golden_cross":      bool(gc),
        "early_trend":       bool(early_cross and not gc),   # MA5>MA20 but MA20<MA60 (회복 초기)
        "volume_confirm":    bool(vol_ratio >= 1.5 or max_vol_5d >= 1.5),
        "rsi_signal":        bool(50 <= rsiv <= 73),          # 오버바이드 상단 73으로 완화
        "rsi_divergence":    bool(rsiv > 45 and ret_5d > 0 and rsiv > rsi_p),
        "rsi_oversold":      bool(rsi_oversold_recovery),
        "bollinger_break":   bool(last > bb_mv),
        "macd_cross":        bool(mlv > msv),
        "macd_turned":       bool(macd_turned),               # MACD 마이너스→플러스 전환
        "stoch_signal":      bool(stkv > 20 and stkv > stdv and v2(stk) < 30),
        "ma_alignment":      bool(ma5v > ma20v and ma20v > ma60v),
        "relative_strength": bool(ret_20d > spy_20d),
        "fib_support":       False,  # 아래 계산
    }

    # 피보나치 지지
    hi60 = float(high.tail(60).max()); lo60 = float(low.tail(60).min())
    d60  = hi60 - lo60
    fib_levels = [hi60 - d60*0.618, hi60 - d60*0.500, hi60 - d60*0.382, hi60 - d60*0.236]
    signals["fib_support"] = any(abs(last - lv) <= 1.5*atrv for lv in fib_levels)

    # ── 점수 계산 (100점 만점 기준) ──────────────────────────────────────────────
    # 이론 최대: 26+17+10+13+10+8+5+4+3+4 = 100pt
    # 실질 최고: 85-95pt (모든 조건 동시 충족 불가)

    score = 0

    # ① 모멘텀 보너스 (SPY 대비 초과 수익) — 최대 26pt
    rs_excess = ret_20d - spy_20d
    if   rs_excess >= 50:  score += 26  # 폭발적 (CRCL +114% 같은) ★
    elif rs_excess >= 35:  score += 22
    elif rs_excess >= 25:  score += 18
    elif rs_excess >= 15:  score += 13
    elif rs_excess >= 8:   score += 8
    elif rs_excess >= 3:   score += 4
    elif rs_excess > 0:    score += 2

    # ② 조기 추세 전환 OR 골든크로스 — 최대 17pt
    if signals["ma_alignment"]:         score += 13  # 완전 정렬 (5>20>60)
    elif gc:                            score += 9   # 골든크로스만
    elif signals["early_trend"]:        score += 6   # MA5>MA20 (회복 초기)

    if gc_recent:                       score += 4   # 최근 돌파 보너스

    # ③ MACD — 최대 10pt
    if macd_turned:                     score += 10  # 마이너스→플러스 전환 (강력) ★
    elif mlv > msv and mhv > mhv2 and mhv2 > mhv3:
        score += 9   # 히스토그램 2봉 연속 가속
    elif mlv > msv and mhv > mhv2:
        score += 6   # 히스토그램 상승
    elif mlv > msv:
        score += 4

    # ④ 거래량 — 최대 13pt
    if   max_vol_5d >= 3.0:  score += 13
    elif max_vol_5d >= 2.0:  score += 10
    elif vol_ratio  >= 2.0:  score += 9
    elif vol_ratio  >= 1.5:  score += 6
    elif vol_ratio  >= 1.2:  score += 2

    # ⑤ RSI — 최대 10pt
    if rsi_oversold_recovery:           score += 10  # 과매도 반등 (저점 매수) ★
    elif 55 <= rsiv <= 70:              score += 10  # 황금 모멘텀 구간
    elif 50 <= rsiv <= 73:              score += 6
    elif rsiv > 73:                     score += 4   # 과열이지만 모멘텀 존재

    # ⑥ 피보나치 지지 — 8pt
    if signals["fib_support"]:          score += 8

    # ⑦ 볼린저 — 최대 5pt
    if last > bb_uv:                    score += 5   # 상단 돌파 = 강한 모멘텀
    elif last > bb_mv:                  score += 3

    # ⑧ 상대강도 — 4pt
    if signals["relative_strength"]:    score += 4

    # ⑨ 스토캐스틱 — 3pt
    if signals["stoch_signal"]:         score += 3

    # ⑩ 52주 신고가 근접 보너스 (5% 이내) — 4pt
    if dist_52w <= 0.05:                score += 4

    # ATR 기반 스윙
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
            "h60": round(hi60,2), "l60": round(lo60,2),
            "r236": round(hi60-d60*0.236,2),
            "r382": round(hi60-d60*0.382,2),
            "r500": round(hi60-d60*0.500,2),
            "r618": round(hi60-d60*0.618,2),
        },
    }

    return {
        "ticker":    ticker,
        "name":      ticker,
        "sector":    "NASDAQ",
        "price":     round(last, 2),
        "change_pct": round((last/float(close.iloc[-2])-1)*100, 2) if len(close)>=2 else 0,
        "score":     score,
        "vol_ratio": round(vol_ratio, 2),
        "atr":       round(atrv, 4),
        "rs_diff":   round(rs_excess, 2),
        "rs_bonus":  min(20, max(0, round(rs_excess/5))),
        "signals": {
            "golden_cross":    signals["golden_cross"],
            "volume_confirm":  signals["volume_confirm"],
            "rsi_signal":      signals["rsi_signal"],
            "rsi_divergence":  signals["rsi_divergence"],
            "bollinger_break": signals["bollinger_break"],
            "macd_cross":      signals["macd_cross"],
            "stoch_signal":    signals["stoch_signal"],
            "ma_alignment":    signals["ma_alignment"],
            "relative_strength": signals["relative_strength"],
            "fib_support":     signals["fib_support"],
            # 추가 신호
            "early_trend":     signals["early_trend"],
            "macd_turned":     signals["macd_turned"],
            "rsi_oversold":    signals["rsi_oversold"],
        },
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
            "rsi": round(rsiv, 1), "macd": round(mlv, 4),
            "macd_cross_recent": bool(macd_turned),
            "golden_cross": bool(gc), "recent_gc": gc_recent,
            "bb_position":  round((last-bb_lv)/(bb_uv-bb_lv+1e-9), 3),
            "stoch_k": round(stkv, 1),
            "dist_52w": round(dist_52w, 4),
            "ret_5d":  round(ret_5d, 2), "ret_20d": round(ret_20d, 2),
            "vol_ratio": round(vol_ratio, 2), "max_vol_5d": round(max_vol_5d, 2),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    print(f"\n{'='*65}")
    print(f" NASDAQ 전체 보물주 스캔  {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*65}\n")

    # SPY 20일 수익률
    spy_20d = 0.0
    try:
        spy_df = yf.download("SPY", period="60d", interval="1d",
                              auto_adjust=True, progress=False)
        if isinstance(spy_df.columns, pd.MultiIndex):
            spy_df.columns = spy_df.columns.get_level_values(0)
        sc = spy_df["Close"].dropna()
        if len(sc) >= 21:
            spy_20d = round(float((sc.iloc[-1]/sc.iloc[-21]-1)*100), 2)
        print(f"SPY 20일 수익률: {spy_20d:+.2f}%\n")
    except Exception as e:
        print(f"SPY 실패: {e}")

    # 종목 리스트 수집
    print("NASDAQ/NYSE 전종목 수집 중...")
    universe = fetch_nasdaq_tickers()
    # 레버리지 제거
    universe = [u for u in universe if not is_leveraged(u["ticker"], u.get("name",""))]
    tickers  = [u["ticker"] for u in universe]
    name_map = {u["ticker"]: u.get("name", u["ticker"]) for u in universe}
    sect_map = {u["ticker"]: u.get("sector", "NASDAQ")  for u in universe}
    print(f"유효 종목: {len(tickers)}개 (레버리지 제외)\n")

    # 배치 다운로드 (50개씩)
    print("OHLCV 배치 다운로드...")
    all_results: list[dict] = []
    BATCH = 50
    failed = 0

    for start in range(0, len(tickers), BATCH):
        batch = tickers[start:start+BATCH]
        batch_num = start//BATCH + 1
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
        except Exception as e:
            # 배치 실패 → 개별 재시도
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
        time.sleep(0.2)  # 서버 부하 완화

    print(f"\n\n총 {len(all_results)}개 통과 | {failed}개 실패/제외")

    if not all_results:
        print("ERROR: 결과 없음")
        return 1

    # 정렬 → TOP 10
    all_results.sort(key=lambda x: x["score"], reverse=True)
    top10 = all_results[:10]

    print(f"\n{'='*65}")
    print(f" 최종 TOP 10 (SPY 20d={spy_20d:+.2f}%)")
    print(f"{'='*65}")
    for i, s in enumerate(top10):
        sigs = s.get("signals", {})
        on   = [k for k,v in sigs.items() if v]
        det  = s.get("details", {})
        print(f" #{i+1:2d} {s['ticker']:<8} {s['score']:3d}점  "
              f"${s['price']:>9.2f}  "
              f"RSI={det.get('rsi',0):.0f}  "
              f"20d={s.get('rs_diff',0)+spy_20d:+.1f}%  "
              f"vol={s['vol_ratio']:.1f}x")
        print(f"      신호({len(on)}): {on}")
    print(f"{'='*65}\n")

    docs_out = {
        "updated_at":   now.strftime("%Y-%m-%d %H:%M KST"),
        "spy_20d":      spy_20d,
        "top100_count": len(all_results),
        "stocks":       top10,
    }
    DOCS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DOCS_JSON.write_text(json.dumps(docs_out, ensure_ascii=False, indent=2))
    print(f"✅ 저장 완료 → {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
