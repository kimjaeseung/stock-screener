#!/usr/bin/env python3
"""
Signal Deck — Technical Analysis Stock Screener
Usage:
  python screener.py           # full scan
  python screener.py --test    # quick test (30 stocks, ~2 min)
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ─── Technical Indicators (manual — no pandas-ta dependency issues) ───────────

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
    return 100 - 100 / (1 + gain / (loss + 1e-10))

def _macd(s: pd.Series, fast=12, slow=26, sig=9):
    line = _ema(s, fast) - _ema(s, slow)
    signal = _ema(line, sig)
    return line, signal, line - signal

def _bbands(s: pd.Series, n=20, k=2.0):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std

def _atr(h: pd.Series, l: pd.Series, c: pd.Series, n=14) -> pd.Series:
    tr = pd.concat(
        [(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _adx(h: pd.Series, l: pd.Series, c: pd.Series, n=14) -> pd.Series:
    tr = pd.concat(
        [(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    dm_p = h.diff().clip(lower=0)
    dm_m = (-l.diff()).clip(lower=0)
    dm_p = dm_p.where(dm_p > dm_m, 0.0)
    dm_m = dm_m.where(dm_m > dm_p, 0.0)
    atr_n = tr.ewm(span=n, adjust=False).mean()
    di_p = 100 * dm_p.ewm(span=n, adjust=False).mean() / (atr_n + 1e-10)
    di_m = 100 * dm_m.ewm(span=n, adjust=False).mean() / (atr_n + 1e-10)
    dx = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
    return dx.ewm(span=n, adjust=False).mean()

def _stoch(h: pd.Series, l: pd.Series, c: pd.Series, k=14, d=3):
    lo = l.rolling(k).min()
    hi = h.rolling(k).max()
    sk = 100 * (c - lo) / (hi - lo + 1e-10)
    return sk, sk.rolling(d).mean()

def compute_indicators(df: pd.DataFrame) -> dict | None:
    """모든 기술적 지표 계산. 데이터 부족 시 None 반환."""
    c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
    if len(c) < 130:
        return None

    ma5   = _sma(c, 5)
    ma20  = _sma(c, 20)
    ma60  = _sma(c, 60)
    ma120 = _sma(c, 120)
    ma200 = _sma(c, 200)

    macd_line, macd_sig, macd_hist = _macd(c)
    rsi14 = _rsi(c, 14)
    bb_u, bb_m, bb_l = _bbands(c, 20, 2.0)
    atr14 = _atr(h, l, c, 14)
    adx14 = _adx(h, l, c, 14)
    stoch_k, stoch_d = _stoch(h, l, c, 14, 3)
    vol_ma20 = _sma(v, 20)

    return {
        'ma5': ma5, 'ma20': ma20, 'ma60': ma60,
        'ma120': ma120, 'ma200': ma200,
        'macd': macd_line, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
        'rsi': rsi14,
        'bb_u': bb_u, 'bb_m': bb_m, 'bb_l': bb_l,
        'atr': atr14,
        'adx': adx14,
        'stoch_k': stoch_k, 'stoch_d': stoch_d,
        'vol_ma20': vol_ma20,
    }


# ─── Scoring (100점 만점) ───────────────────────────────────────────────────────

def score_stock(df: pd.DataFrame, ind: dict) -> dict | None:
    """점수 산출 + 시그널 수집. 유효하지 않으면 None."""
    close_s  = float(df['Close'].iloc[-1])
    prev_cls = float(df['Close'].iloc[-2])

    def v(key): return float(ind[key].iloc[-1])
    def vp(key): return float(ind[key].iloc[-2])

    ma5   = v('ma5');  ma20  = v('ma20');  ma60  = v('ma60')
    ma120 = v('ma120'); ma200 = v('ma200')
    rsi   = v('rsi');  adx   = v('adx')
    macd  = v('macd'); macd_sig = v('macd_sig')
    bb_u  = v('bb_u'); bb_l  = v('bb_l')
    stk   = v('stoch_k'); std_ = v('stoch_d')
    vol   = float(df['Volume'].iloc[-1])
    vol_avg = float(ind['vol_ma20'].iloc[-1])
    vol_ratio = vol / (vol_avg + 1)

    if any(np.isnan(x) for x in [ma5,ma20,ma60,ma120,ma200,rsi,adx,macd,bb_u]):
        return None

    score = 0
    breakdown = {'trend': 0, 'golden_cross': 0, 'momentum': 0,
                 'volume': 0, 'support': 0, 'bollinger': 0}
    signals = []

    # ── 1. 추세 (25점) ──
    if ma5 > ma20 > ma60 > ma120:
        breakdown['trend'] += 10
        signals.append('이평선 정배열 (5>20>60>120)')
    elif ma5 > ma20 > ma60:
        breakdown['trend'] += 5
        signals.append('단기 이평선 정배열 (5>20>60)')
    if close_s > ma200:
        breakdown['trend'] += 5
        signals.append(f'200일선 위 (MA200={ma200:.1f})')
    if adx > 25:
        breakdown['trend'] += 5
        signals.append(f'ADX {adx:.1f} — 강한 추세')
    # 20일선 기울기 양수 (5일 전 대비)
    ma20_5ago = float(ind['ma20'].iloc[-6]) if len(ind['ma20']) >= 6 else ma20
    if ma20 > ma20_5ago * 1.005:
        breakdown['trend'] += 5
        signals.append('20일선 상승 기울기')
    breakdown['trend'] = min(breakdown['trend'], 25)

    # ── 2. 골든크로스 (20점) ──
    gc_earned = 0
    # 5일/20일 골든크로스 (최근 5봉)
    for i in range(-5, 0):
        try:
            if float(ind['ma5'].iloc[i-1]) < float(ind['ma20'].iloc[i-1]) \
               and float(ind['ma5'].iloc[i]) >= float(ind['ma20'].iloc[i]):
                gc_earned = max(gc_earned, 10)
                signals.append('5일선 × 20일선 골든크로스')
                break
        except IndexError:
            pass
    # 20일/60일 골든크로스 (최근 10봉)
    for i in range(-10, 0):
        try:
            if float(ind['ma20'].iloc[i-1]) < float(ind['ma60'].iloc[i-1]) \
               and float(ind['ma20'].iloc[i]) >= float(ind['ma60'].iloc[i]):
                gc_earned = max(gc_earned, 10)
                signals.append('20일선 × 60일선 골든크로스')
                break
        except IndexError:
            pass
    # MACD 골든크로스 (최근 3봉)
    for i in range(-3, 0):
        try:
            if float(ind['macd'].iloc[i-1]) < float(ind['macd_sig'].iloc[i-1]) \
               and float(ind['macd'].iloc[i]) >= float(ind['macd_sig'].iloc[i]):
                gc_earned = max(gc_earned, 10)
                signals.append('MACD 골든크로스')
                break
        except IndexError:
            pass
    # 현재 MACD > Signal (+5)
    if macd > macd_sig:
        gc_earned = max(gc_earned, 5)
        if 'MACD 골든크로스' not in ' '.join(signals):
            signals.append('MACD 강세 (MACD > Signal)')
    breakdown['golden_cross'] = min(gc_earned, 20)

    # ── 3. 모멘텀 (20점) ──
    if 40 <= rsi <= 60:
        breakdown['momentum'] += 5
        signals.append(f'RSI {rsi:.0f} (적정 구간)')
    elif rsi < 30:
        rsi_series = ind['rsi'].dropna()
        if len(rsi_series) >= 3 and any(rsi_series.iloc[-5:-1] < 30) and rsi > 30:
            breakdown['momentum'] += 10
            signals.append(f'RSI {rsi:.0f} — 과매도 탈출 반등')
        else:
            breakdown['momentum'] += 3
    elif 30 <= rsi < 40:
        breakdown['momentum'] += 3
        signals.append(f'RSI {rsi:.0f} (저평가 구간)')
    # 스토캐스틱 상향 돌파
    if not np.isnan(stk) and not np.isnan(std_):
        prev_stk = float(ind['stoch_k'].iloc[-2])
        prev_std = float(ind['stoch_d'].iloc[-2])
        if prev_stk < prev_std and stk >= std_:
            breakdown['momentum'] += 5
            signals.append(f'스토캐스틱 %K({stk:.0f}) 상향 돌파')
    # MACD 히스토그램 증가
    mh = ind['macd_hist']
    if len(mh) >= 3 and not np.isnan(float(mh.iloc[-1])):
        if float(mh.iloc[-1]) > float(mh.iloc[-2]) > float(mh.iloc[-3]):
            breakdown['momentum'] += 5
            signals.append('MACD 히스토그램 연속 증가')
    breakdown['momentum'] = min(breakdown['momentum'], 20)

    # ── 4. 거래량 (15점) ──
    if vol_ratio >= 2.0:
        breakdown['volume'] += 10
        signals.append(f'거래량 {vol_ratio:.1f}배 급증')
    elif vol_ratio >= 1.5:
        breakdown['volume'] += 5
        signals.append(f'거래량 {vol_ratio:.1f}배 증가')
    if close_s > prev_cls and vol > vol_avg:
        breakdown['volume'] += 5
        if f'거래량' not in ' '.join(signals):
            signals.append('거래량 증가 + 주가 상승')
    breakdown['volume'] = min(breakdown['volume'], 15)

    # ── 5. 지지/저항 & 피보나치 (10점) ──
    recent_high = float(df['High'].tail(60).max())
    recent_low  = float(df['Low'].tail(60).min())
    fib_diff = recent_high - recent_low
    fib382 = recent_high - fib_diff * 0.382
    fib618 = recent_high - fib_diff * 0.618
    if fib618 <= close_s <= fib382:
        breakdown['support'] += 5
        signals.append('피보나치 38.2%~61.8% 지지 구간')
    # 볼린저 하단 반등
    recent_5 = df['Low'].tail(5)
    if not np.isnan(bb_l) and any(recent_5 <= bb_l * 1.005) and close_s > bb_l:
        breakdown['support'] += 5
        signals.append('볼린저 밴드 하단 반등')
    # MA 지지
    if abs(close_s - ma20) / ma20 < 0.02:
        breakdown['support'] = min(breakdown['support'] + 5, 10)
        signals.append('20일선 지지 확인')
    elif abs(close_s - ma60) / ma60 < 0.02:
        breakdown['support'] = min(breakdown['support'] + 5, 10)
        signals.append('60일선 지지 확인')
    breakdown['support'] = min(breakdown['support'], 10)

    # ── 6. 볼린저 스퀴즈 (10점) ──
    bb_width = ind['bb_u'] - ind['bb_l']
    bb_width_recent = bb_width.dropna().tail(120)
    if len(bb_width_recent) >= 20:
        curr_width = float(bb_width.iloc[-1])
        pct = (bb_width_recent < curr_width).sum() / len(bb_width_recent)
        if pct <= 0.20:
            breakdown['bollinger'] += 5
            signals.append(f'볼린저 스퀴즈 (BB폭 하위 {pct*100:.0f}%)')
            # 스퀴즈 후 상단 돌파
            if close_s > bb_u and prev_cls <= float(ind['bb_u'].iloc[-2]):
                breakdown['bollinger'] += 5
                signals.append('볼린저 스퀴즈 후 상단 돌파')
    breakdown['bollinger'] = min(breakdown['bollinger'], 10)

    total = sum(breakdown.values())
    return {
        'total': total,
        'breakdown': breakdown,
        'signals': signals[:6],
    }


def calc_risk_reward(df: pd.DataFrame, ind: dict, is_kr: bool) -> dict | None:
    """진입/손절/목표가 + 손익비 계산. 1.5 미만이면 None."""
    close = float(df['Close'].iloc[-1])
    atr   = float(ind['atr'].iloc[-1])
    bb_u  = float(ind['bb_u'].iloc[-1])
    bb_l  = float(ind['bb_l'].iloc[-1])

    # 손절가: max(현재가 - 2*ATR, 최근 20일 최저가) — 현재가에 가까운 값
    low_20  = float(df['Low'].tail(20).min())
    stop_candidates = [close - 2.0 * atr, low_20]
    valid_stops = [s for s in stop_candidates if 0 < s < close * 0.98]
    if not valid_stops:
        return None
    stop_loss = max(valid_stops)  # 현재가에 더 가까운(높은) 값

    # 목표가: min(최근 60일 최고가, 볼린저 상단)
    high_60 = float(df['High'].tail(60).max())
    target_candidates = [high_60, bb_u * 1.01]
    valid_targets = [t for t in target_candidates if t > close * 1.02]
    if not valid_targets:
        return None
    take_profit = min(valid_targets)

    risk   = close - stop_loss
    reward = take_profit - close
    if risk <= 0:
        return None
    ratio = reward / risk
    if ratio < 1.5:
        return None

    fmt = lambda x: round(x, 0) if is_kr else round(x, 2)
    return {
        'entry':       fmt(close),
        'stop_loss':   fmt(stop_loss),
        'take_profit': fmt(take_profit),
        'risk':        fmt(risk),
        'reward':      fmt(reward),
        'ratio':       round(ratio, 2),
        'risk_pct':    round((stop_loss - close) / close * 100, 1),
        'reward_pct':  round((take_profit - close) / close * 100, 1),
    }


# ─── Universe ──────────────────────────────────────────────────────────────────

def get_sp500_tickers() -> list[dict]:
    """Wikipedia에서 S&P 500 티커 파싱"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(requests.get(url, timeout=15).text)
        df = tables[0]
        results = []
        for _, row in df.iterrows():
            ticker = str(row.get('Symbol', row.get('Ticker symbol', ''))).replace('.', '-')
            name   = str(row.get('Security', row.get('Company', '')))
            sector = str(row.get('GICS Sector', 'Unknown'))
            if ticker:
                results.append({'ticker': ticker, 'name': name,
                                 'market': 'NYSE/NASDAQ', 'sector': sector})
        print(f"  S&P 500: {len(results)}개 종목 로드")
        return results
    except Exception as e:
        print(f"  Wikipedia 파싱 실패 ({e}), 기본 목록 사용")
        return US_FALLBACK

def get_kr_tickers() -> list[dict]:
    """FinanceDataReader로 코스피+코스닥 종목 로드"""
    try:
        import FinanceDataReader as fdr
        results = []
        for market, suffix in [('KOSPI', 'KS'), ('KOSDAQ', 'KQ')]:
            listing = fdr.StockListing(market)
            # 시총 필터 (5000억 이상)
            if 'Marcap' in listing.columns:
                listing = listing[listing['Marcap'] >= 500_000_000_000]
            # 거래대금 필터 (있을 경우)
            if 'Amount' in listing.columns:
                listing = listing[listing['Amount'] >= 5_000_000_000]
            for _, row in listing.iterrows():
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6)
                name = str(row.get('Name', ''))
                sector = str(row.get('Sector', row.get('Industry', '기타')))
                if code and name:
                    results.append({
                        'ticker': f'{code}.{suffix}',
                        'name': name,
                        'market': market,
                        'sector': sector,
                    })
        print(f"  KR: {len(results)}개 종목 로드 (시총 5000억+)")
        return results
    except Exception as e:
        print(f"  FinanceDataReader 실패 ({e}), 기본 목록 사용")
        return KR_FALLBACK


# ─── Fallback lists ─────────────────────────────────────────────────────────────

KR_FALLBACK = [
    {'ticker':'005930.KS','name':'삼성전자','market':'KOSPI','sector':'반도체'},
    {'ticker':'000660.KS','name':'SK하이닉스','market':'KOSPI','sector':'반도체'},
    {'ticker':'035420.KS','name':'NAVER','market':'KOSPI','sector':'인터넷'},
    {'ticker':'035720.KS','name':'카카오','market':'KOSPI','sector':'인터넷'},
    {'ticker':'005380.KS','name':'현대차','market':'KOSPI','sector':'자동차'},
    {'ticker':'000270.KS','name':'기아','market':'KOSPI','sector':'자동차'},
    {'ticker':'051910.KS','name':'LG화학','market':'KOSPI','sector':'화학'},
    {'ticker':'006400.KS','name':'삼성SDI','market':'KOSPI','sector':'2차전지'},
    {'ticker':'373220.KS','name':'LG에너지솔루션','market':'KOSPI','sector':'2차전지'},
    {'ticker':'207940.KS','name':'삼성바이오로직스','market':'KOSPI','sector':'바이오'},
    {'ticker':'068270.KS','name':'셀트리온','market':'KOSPI','sector':'바이오'},
    {'ticker':'003550.KS','name':'LG','market':'KOSPI','sector':'지주'},
    {'ticker':'012330.KS','name':'현대모비스','market':'KOSPI','sector':'자동차부품'},
    {'ticker':'028260.KS','name':'삼성물산','market':'KOSPI','sector':'건설'},
    {'ticker':'034730.KS','name':'SK','market':'KOSPI','sector':'지주'},
    {'ticker':'015760.KS','name':'한국전력','market':'KOSPI','sector':'전기'},
    {'ticker':'032830.KS','name':'삼성생명','market':'KOSPI','sector':'보험'},
    {'ticker':'003490.KS','name':'대한항공','market':'KOSPI','sector':'항공'},
    {'ticker':'259960.KS','name':'크래프톤','market':'KOSPI','sector':'게임'},
    {'ticker':'036570.KS','name':'NCsoft','market':'KOSPI','sector':'게임'},
    {'ticker':'018260.KS','name':'삼성SDS','market':'KOSPI','sector':'IT서비스'},
    {'ticker':'009150.KS','name':'삼성전기','market':'KOSPI','sector':'전기전자'},
    {'ticker':'000810.KS','name':'삼성화재','market':'KOSPI','sector':'보험'},
    {'ticker':'096770.KS','name':'SK이노베이션','market':'KOSPI','sector':'에너지'},
    {'ticker':'011200.KS','name':'HMM','market':'KOSPI','sector':'해운'},
    {'ticker':'086520.KQ','name':'에코프로','market':'KOSDAQ','sector':'2차전지소재'},
    {'ticker':'247540.KQ','name':'에코프로비엠','market':'KOSDAQ','sector':'2차전지소재'},
    {'ticker':'196170.KQ','name':'알테오젠','market':'KOSDAQ','sector':'바이오'},
    {'ticker':'357780.KQ','name':'솔브레인','market':'KOSDAQ','sector':'반도체소재'},
    {'ticker':'041510.KQ','name':'SM엔터','market':'KOSDAQ','sector':'엔터'},
    {'ticker':'035900.KQ','name':'JYP Ent','market':'KOSDAQ','sector':'엔터'},
    {'ticker':'263750.KQ','name':'펄어비스','market':'KOSDAQ','sector':'게임'},
    {'ticker':'091990.KQ','name':'셀트리온헬스케어','market':'KOSDAQ','sector':'바이오'},
    {'ticker':'293490.KQ','name':'카카오게임즈','market':'KOSDAQ','sector':'게임'},
    {'ticker':'112040.KQ','name':'위메이드','market':'KOSDAQ','sector':'게임'},
]

US_FALLBACK = [
    {'ticker':'AAPL','name':'Apple','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MSFT','name':'Microsoft','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NVDA','name':'NVIDIA','market':'NASDAQ','sector':'Technology'},
    {'ticker':'GOOGL','name':'Alphabet','market':'NASDAQ','sector':'Technology'},
    {'ticker':'AMZN','name':'Amazon','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'META','name':'Meta Platforms','market':'NASDAQ','sector':'Technology'},
    {'ticker':'TSLA','name':'Tesla','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'AMD','name':'AMD','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NFLX','name':'Netflix','market':'NASDAQ','sector':'Communication Services'},
    {'ticker':'AVGO','name':'Broadcom','market':'NASDAQ','sector':'Technology'},
    {'ticker':'JPM','name':'JPMorgan Chase','market':'NYSE','sector':'Financials'},
    {'ticker':'V','name':'Visa','market':'NYSE','sector':'Financials'},
    {'ticker':'MA','name':'Mastercard','market':'NYSE','sector':'Financials'},
    {'ticker':'UNH','name':'UnitedHealth','market':'NYSE','sector':'Health Care'},
    {'ticker':'LLY','name':'Eli Lilly','market':'NYSE','sector':'Health Care'},
    {'ticker':'JNJ','name':'Johnson & Johnson','market':'NYSE','sector':'Health Care'},
    {'ticker':'XOM','name':'ExxonMobil','market':'NYSE','sector':'Energy'},
    {'ticker':'WMT','name':'Walmart','market':'NYSE','sector':'Consumer Staples'},
    {'ticker':'PG','name':'Procter & Gamble','market':'NYSE','sector':'Consumer Staples'},
    {'ticker':'ORCL','name':'Oracle','market':'NYSE','sector':'Technology'},
    {'ticker':'CRM','name':'Salesforce','market':'NYSE','sector':'Technology'},
    {'ticker':'ADBE','name':'Adobe','market':'NASDAQ','sector':'Technology'},
    {'ticker':'QCOM','name':'Qualcomm','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MU','name':'Micron Technology','market':'NASDAQ','sector':'Technology'},
    {'ticker':'INTC','name':'Intel','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NOW','name':'ServiceNow','market':'NYSE','sector':'Technology'},
    {'ticker':'PANW','name':'Palo Alto Networks','market':'NASDAQ','sector':'Technology'},
    {'ticker':'CRWD','name':'CrowdStrike','market':'NASDAQ','sector':'Technology'},
    {'ticker':'PLTR','name':'Palantir','market':'NYSE','sector':'Technology'},
    {'ticker':'ARM','name':'Arm Holdings','market':'NASDAQ','sector':'Technology'},
    {'ticker':'COIN','name':'Coinbase','market':'NASDAQ','sector':'Financials'},
    {'ticker':'GS','name':'Goldman Sachs','market':'NYSE','sector':'Financials'},
    {'ticker':'BAC','name':'Bank of America','market':'NYSE','sector':'Financials'},
    {'ticker':'UBER','name':'Uber','market':'NYSE','sector':'Industrials'},
    {'ticker':'TSM','name':'TSMC','market':'NYSE','sector':'Technology'},
]

US_TEST = US_FALLBACK[:20]
KR_TEST = KR_FALLBACK[:20]


# ─── Single ticker analysis ────────────────────────────────────────────────────

def analyze(info: dict, is_kr: bool) -> dict | None:
    ticker = info['ticker']
    try:
        raw = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if raw is None or len(raw) < 130:
            return None
        # MultiIndex 정리
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw[['Open','High','Low','Close','Volume']].dropna()
        if len(df) < 130:
            return None
        # 거래량 없으면 스킵
        if df['Volume'].tail(20).mean() < 1000:
            return None

        ind = compute_indicators(df)
        if ind is None:
            return None

        score_result = score_stock(df, ind)
        if score_result is None:
            return None

        rr = calc_risk_reward(df, ind, is_kr)
        if rr is None:
            return None

        close    = float(df['Close'].iloc[-1])
        prev_cls = float(df['Close'].iloc[-2])
        change_pct = (close - prev_cls) / prev_cls * 100

        price_hist = [round(float(p), 2) for p in df['Close'].tail(30)]

        def _f(key): return float(ind[key].iloc[-1])
        rsi_val  = _f('rsi')
        macd_val = _f('macd')
        macds_val= _f('macd_sig')
        adx_val  = _f('adx')
        bb_u = _f('bb_u'); bb_l = _f('bb_l')
        bb_pos = (close - bb_l) / (bb_u - bb_l + 1e-10)
        vol_ratio = float(df['Volume'].iloc[-1]) / (float(ind['vol_ma20'].iloc[-1]) + 1)

        ma200 = _f('ma200')
        checklist = {
            'above_ma200':         bool(close > ma200 and ma200 > 0),
            'golden_cross_recent': bool(score_result['breakdown']['golden_cross'] >= 10),
            'volume_surge':        bool(vol_ratio >= 1.5),
            'rsi_healthy':         bool(30 <= rsi_val <= 70),
            'macd_bullish':        bool(macd_val > macds_val),
            'trend_strong':        bool(score_result['breakdown']['trend'] >= 15),
            'rr_ratio_good':       bool(rr['ratio'] >= 2.0),
        }

        return {
            'ticker':    ticker,
            'name':      info['name'],
            'market':    info['market'],
            'sector':    info.get('sector', 'Unknown'),
            'price':     round(close, 0) if is_kr else round(close, 2),
            'change_pct': round(change_pct, 1),
            'score':     score_result['total'],
            'score_breakdown': score_result['breakdown'],
            'signals':   score_result['signals'],
            'technicals': {
                'rsi_14':       round(rsi_val, 1),
                'macd':         round(macd_val, 4),
                'macd_signal':  round(macds_val, 4),
                'adx':          round(adx_val, 1),
                'volume_ratio': round(vol_ratio, 1),
                'bb_position':  round(min(max(bb_pos, 0), 1), 2),
            },
            'risk_reward':      rr,
            'price_history_30d': price_hist,
            'ma_20': round(_f('ma20'), 2),
            'ma_60': round(_f('ma60'), 2),
            'checklist': checklist,
        }

    except Exception:
        return None


# ─── Market summary ─────────────────────────────────────────────────────────────

def get_market_summary() -> dict:
    indices = {
        'kospi':  '^KS11',
        'kosdaq': '^KQ11',
        'sp500':  '^GSPC',
        'nasdaq': '^IXIC',
    }
    result = {}
    for key, sym in indices.items():
        try:
            d = yf.download(sym, period='5d', progress=False, auto_adjust=True)
            if d is not None and len(d) >= 2:
                curr = float(d['Close'].iloc[-1])
                prev = float(d['Close'].iloc[-2])
                result[key] = {
                    'index':      round(curr, 2),
                    'change_pct': round((curr - prev) / prev * 100, 2),
                }
            else:
                result[key] = {'index': 0, 'change_pct': 0}
        except Exception:
            result[key] = {'index': 0, 'change_pct': 0}
        time.sleep(0.2)
    return result


# ─── JSON serializer ─────────────────────────────────────────────────────────────

def _default(obj):
    if isinstance(obj, (np.integer,)):  return int(obj)
    if isinstance(obj, (np.floating,)): return float(obj)
    if isinstance(obj, np.ndarray):     return obj.tolist()
    if isinstance(obj, (np.bool_,)):    return bool(obj)
    raise TypeError(f'{type(obj)} not serializable')


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true',
                        help='빠른 테스트: 각 시장 상위 20종목만 스캔')
    parser.add_argument('--kr-only', action='store_true', help='한국 시장만 스캔')
    parser.add_argument('--us-only', action='store_true', help='미국 시장만 스캔')
    args = parser.parse_args()

    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    print(f"\n{'='*60}")
    print(f" Signal Deck Screener  {now.strftime('%Y-%m-%d %H:%M KST')}")
    if args.test:
        print(f" MODE: TEST (각 시장 20종목)")
    print(f"{'='*60}\n")

    # ── 시장 지수 ──
    print("📊 시장 지수 수집...")
    market_summary = get_market_summary()
    for k, v in market_summary.items():
        print(f"  {k.upper():8s} {v['index']:>10.2f}  ({v['change_pct']:+.2f}%)")

    results = {'kr': [], 'us': []}

    # ── 한국 ──
    if not args.us_only:
        print("\n🇰🇷  한국 종목 스캔...")
        kr_list = KR_TEST if args.test else get_kr_tickers()
        kr_cands = []
        for i, info in enumerate(kr_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(kr_list)}] {info['ticker']:<14} {info['name']:<14}")
            sys.stdout.flush()
            result = analyze(info, is_kr=True)
            if result:
                kr_cands.append(result)
                sys.stdout.write(f"  ✅ score={result['score']}  R:R={result['risk_reward']['ratio']:.2f}")
            time.sleep(0.4)
        print()
        kr_top = sorted(kr_cands, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(kr_top):
            s['rank'] = i + 1
        results['kr'] = kr_top
        print(f"  → KR TOP {len(kr_top)}: {[s['name'] for s in kr_top]}")

    # ── 미국 ──
    if not args.kr_only:
        print("\n🇺🇸  미국 종목 스캔...")
        us_list = US_TEST if args.test else get_sp500_tickers()
        us_cands = []
        for i, info in enumerate(us_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(us_list)}] {info['ticker']:<8} {info['name']:<20}")
            sys.stdout.flush()
            result = analyze(info, is_kr=False)
            if result:
                us_cands.append(result)
                sys.stdout.write(f"  ✅ score={result['score']}  R:R={result['risk_reward']['ratio']:.2f}")
            time.sleep(0.4)
        print()
        us_top = sorted(us_cands, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(us_top):
            s['rank'] = i + 1
        results['us'] = us_top
        print(f"  → US TOP {len(us_top)}: {[s['ticker'] for s in us_top]}")

    # ── 저장 ──
    output = {
        'updated_at': now.isoformat(),
        'market_summary': market_summary,
        'screening_results': results,
    }

    out_dir = Path(__file__).parent.parent / 'public' / 'data'
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = out_dir / 'latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=_default)
    print(f"\n✅ 저장 완료: {latest}")

    today = now.strftime('%Y-%m-%d')
    archive = out_dir / f'{today}.json'
    with open(archive, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=_default)
    print(f"✅ 아카이브: {archive}")

    # 7일 초과 아카이브 삭제
    for old in sorted(out_dir.glob('????-??-??.json'))[:-7]:
        old.unlink()
        print(f"🗑️  삭제: {old.name}")

    print(f"\n🎉 완료!  KR {len(results['kr'])}개 + US {len(results['us'])}개\n")


if __name__ == '__main__':
    main()
