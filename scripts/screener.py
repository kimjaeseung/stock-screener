#!/usr/bin/env python3
"""
Signal Deck — Technical Analysis Stock Screener
Usage:
  python screener.py           # full scan (~500 US + ~300 KR)
  python screener.py --test    # quick test (top 40 each, ~3 min)
  python screener.py --kr-only / --us-only
"""

import argparse
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

# ─── Technical Indicators ─────────────────────────────────────────────────────

def _sma(s, n):  return s.rolling(n).mean()
def _ema(s, n):  return s.ewm(span=n, adjust=False).mean()

def _rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(com=n-1, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(com=n-1, adjust=False).mean()
    return 100 - 100 / (1 + g / (l + 1e-10))

def _macd(s, fast=12, slow=26, sig=9):
    line = _ema(s, fast) - _ema(s, slow)
    signal = _ema(line, sig)
    return line, signal, line - signal

def _bbands(s, n=20, k=2.0):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k*std, mid, mid - k*std

def _atr(h, l, c, n=14):
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _adx(h, l, c, n=14):
    tr  = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    dm_p = h.diff().clip(lower=0)
    dm_m = (-l.diff()).clip(lower=0)
    dm_p = dm_p.where(dm_p > dm_m, 0.0)
    dm_m = dm_m.where(dm_m >= dm_p, 0.0)
    atr_n = tr.ewm(span=n, adjust=False).mean()
    di_p  = 100 * dm_p.ewm(span=n, adjust=False).mean() / (atr_n + 1e-10)
    di_m  = 100 * dm_m.ewm(span=n, adjust=False).mean() / (atr_n + 1e-10)
    dx    = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
    return dx.ewm(span=n, adjust=False).mean()

def _stoch(h, l, c, k=14, d=3):
    lo = l.rolling(k).min()
    hi = h.rolling(k).max()
    sk = 100 * (c - lo) / (hi - lo + 1e-10)
    return sk, sk.rolling(d).mean()

def compute_indicators(df: pd.DataFrame) -> dict | None:
    if len(df) < 130:
        return None
    c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
    macd_line, macd_sig, macd_hist = _macd(c)
    bb_u, bb_m, bb_l = _bbands(c, 20, 2.0)
    stoch_k, stoch_d = _stoch(h, l, c, 14, 3)
    # vol_ma20: 오늘 제외 이전 20일 (정확한 비율 계산용)
    vol_ma20_prior = v.shift(1).rolling(20).mean()
    return {
        'ma5': _sma(c,5), 'ma20': _sma(c,20), 'ma60': _sma(c,60),
        'ma120': _sma(c,120), 'ma200': _sma(c,200),
        'macd': macd_line, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
        'rsi': _rsi(c,14),
        'bb_u': bb_u, 'bb_m': bb_m, 'bb_l': bb_l,
        'atr': _atr(h,l,c,14),
        'adx': _adx(h,l,c,14),
        'stoch_k': stoch_k, 'stoch_d': stoch_d,
        'vol_ma20_prior': vol_ma20_prior,
    }


# ─── Scoring (100점 만점) ──────────────────────────────────────────────────────
# 배점: trend 25 / golden_cross 20 / momentum 15 / volume 20 / support 10 / bollinger 10

def score_stock(df: pd.DataFrame, ind: dict) -> dict | None:
    close  = float(df['Close'].iloc[-1])
    prev   = float(df['Close'].iloc[-2])
    vol    = float(df['Volume'].iloc[-1])
    vol_prior_avg = float(ind['vol_ma20_prior'].iloc[-1])
    vol_ratio = vol / (vol_prior_avg + 1)

    def v(k):  return float(ind[k].iloc[-1])
    def vp(k): return float(ind[k].iloc[-2])

    ma5=v('ma5'); ma20=v('ma20'); ma60=v('ma60'); ma120=v('ma120'); ma200=v('ma200')
    rsi=v('rsi'); adx=v('adx')
    macd=v('macd'); msig=v('macd_sig'); mhist=v('macd_hist')
    bb_u=v('bb_u'); bb_l=v('bb_l')
    stk=v('stoch_k'); std_=v('stoch_d')

    if any(np.isnan(x) for x in [ma5,ma20,ma60,ma120,ma200,rsi,adx,macd,bb_u]):
        return None

    score = 0
    bd = {'trend':0,'golden_cross':0,'momentum':0,'volume':0,'support':0,'bollinger':0}
    signals = []

    # ── 1. 추세 (25점) ────────────────────────────────────────────────────────
    if ma5 > ma20 > ma60 > ma120:
        bd['trend'] += 10; signals.append('이평선 정배열 (5>20>60>120)')
    elif ma5 > ma20 > ma60:
        bd['trend'] += 5;  signals.append('단기 이평선 정배열 (5>20>60)')
    if close > ma200:
        bd['trend'] += 5;  signals.append(f'200일선 위')
    if adx > 25:
        bd['trend'] += 5;  signals.append(f'ADX {adx:.0f} — 강한 추세')
    ma20_5ago = float(ind['ma20'].iloc[-6]) if len(ind['ma20'].dropna()) >= 6 else ma20
    if ma20 > ma20_5ago * 1.003:
        bd['trend'] += 5;  signals.append('20일선 상승 중')
    bd['trend'] = min(bd['trend'], 25)

    # ── 2. 골든크로스 (20점) ──────────────────────────────────────────────────
    gc = 0
    for i in range(-5, 0):
        try:
            if float(ind['ma5'].iloc[i-1]) < float(ind['ma20'].iloc[i-1]) \
               and float(ind['ma5'].iloc[i]) >= float(ind['ma20'].iloc[i]):
                gc = max(gc, 10); signals.append('5일선 × 20일선 골든크로스'); break
        except: pass
    for i in range(-10, 0):
        try:
            if float(ind['ma20'].iloc[i-1]) < float(ind['ma60'].iloc[i-1]) \
               and float(ind['ma20'].iloc[i]) >= float(ind['ma60'].iloc[i]):
                gc = max(gc, 10); signals.append('20일선 × 60일선 골든크로스'); break
        except: pass
    for i in range(-3, 0):
        try:
            if float(ind['macd'].iloc[i-1]) < float(ind['macd_sig'].iloc[i-1]) \
               and float(ind['macd'].iloc[i]) >= float(ind['macd_sig'].iloc[i]):
                gc = max(gc, 10); signals.append('MACD 골든크로스'); break
        except: pass
    if macd > msig:
        gc = max(gc, 5)
        if gc < 10: signals.append('MACD > Signal (강세)')
    bd['golden_cross'] = min(gc, 20)

    # ── 3. 모멘텀 (15점) ──────────────────────────────────────────────────────
    if 40 <= rsi <= 60:
        bd['momentum'] += 5; signals.append(f'RSI {rsi:.0f} (적정)')
    elif rsi < 30:
        rsi_s = ind['rsi'].dropna()
        if len(rsi_s) >= 5 and (rsi_s.iloc[-5:-1] < 30).any() and rsi > 30:
            bd['momentum'] += 10; signals.append(f'RSI {rsi:.0f} — 과매도 탈출')
        else:
            bd['momentum'] += 2
    elif 30 <= rsi < 40:
        bd['momentum'] += 3; signals.append(f'RSI {rsi:.0f} (저평가 구간)')
    if not np.isnan(stk) and not np.isnan(std_):
        if vp('stoch_k') < vp('stoch_d') and stk >= std_:
            bd['momentum'] += 5; signals.append(f'스토캐스틱 %K({stk:.0f}) 상향 돌파')
    mh = ind['macd_hist'].dropna()
    if len(mh) >= 3 and float(mh.iloc[-1]) > float(mh.iloc[-2]) > float(mh.iloc[-3]):
        bd['momentum'] += 5; signals.append('MACD 히스토그램 연속 증가')
    bd['momentum'] = min(bd['momentum'], 15)

    # ── 4. 거래량 (20점) — 거래량 급증 종목 우대 ─────────────────────────────
    if vol_ratio >= 3.0:
        bd['volume'] += 20; signals.append(f'거래량 {vol_ratio:.1f}배 폭발 🔥')
    elif vol_ratio >= 2.0:
        bd['volume'] += 14; signals.append(f'거래량 {vol_ratio:.1f}배 급증')
    elif vol_ratio >= 1.5:
        bd['volume'] += 8;  signals.append(f'거래량 {vol_ratio:.1f}배 증가')
    elif vol_ratio >= 1.2:
        bd['volume'] += 4
    if close > prev and vol_ratio >= 1.2:
        bd['volume'] = min(bd['volume'] + 6, 20)
        if not any('급증' in s or '증가' in s or '폭발' in s for s in signals):
            signals.append('거래량+주가 동반 상승')
    bd['volume'] = min(bd['volume'], 20)

    # ── 5. 지지/저항 & 피보나치 (10점) ────────────────────────────────────────
    hi60  = float(df['High'].tail(60).max())
    lo60  = float(df['Low'].tail(60).min())
    diff  = hi60 - lo60
    f382  = hi60 - diff * 0.382
    f618  = hi60 - diff * 0.618
    if f618 <= close <= f382:
        bd['support'] += 5; signals.append('피보나치 38.2%~61.8% 지지')
    if not np.isnan(bb_l) and (df['Low'].tail(5) <= bb_l * 1.008).any() and close > bb_l:
        bd['support'] += 5; signals.append('볼린저 밴드 하단 반등')
    if abs(close - ma20) / ma20 < 0.015:
        bd['support'] = min(bd['support'] + 5, 10); signals.append('20일선 지지')
    elif abs(close - ma60) / ma60 < 0.015:
        bd['support'] = min(bd['support'] + 5, 10); signals.append('60일선 지지')
    bd['support'] = min(bd['support'], 10)

    # ── 6. 볼린저 스퀴즈 (10점) ───────────────────────────────────────────────
    bw = (ind['bb_u'] - ind['bb_l']).dropna()
    if len(bw) >= 20:
        pct = (bw.tail(120) < float(bw.iloc[-1])).sum() / min(len(bw), 120)
        if pct <= 0.20:
            bd['bollinger'] += 5; signals.append(f'볼린저 스퀴즈 (BB폭 하위 {pct*100:.0f}%)')
            if close > float(ind['bb_u'].iloc[-1]) and prev <= float(ind['bb_u'].iloc[-2]):
                bd['bollinger'] += 5; signals.append('스퀴즈 후 상단 돌파 🚀')
    bd['bollinger'] = min(bd['bollinger'], 10)

    total = sum(bd.values())
    return {'total': total, 'breakdown': bd, 'signals': signals[:6]}


# ─── Risk/Reward ──────────────────────────────────────────────────────────────

def calc_risk_reward(df: pd.DataFrame, ind: dict, is_kr: bool) -> dict | None:
    close = float(df['Close'].iloc[-1])
    atr   = float(ind['atr'].iloc[-1])
    bb_u  = float(ind['bb_u'].iloc[-1])
    lo20  = float(df['Low'].tail(20).min())

    # 손절: max(현재가 - 2*ATR, 최근 20일 최저가)
    stops = [close - 2.0 * atr, lo20]
    valid_stops = [s for s in stops if 0 < s < close * 0.97]
    if not valid_stops: return None
    stop = max(valid_stops)

    # 목표: min(최근 60일 최고가, 볼린저 상단)
    hi60 = float(df['High'].tail(60).max())
    tgts = [hi60, bb_u * 1.01]
    valid_tgts = [t for t in tgts if t > close * 1.02]
    if not valid_tgts: return None
    tp = min(valid_tgts)

    risk = close - stop
    reward = tp - close
    if risk <= 0: return None
    ratio = reward / risk
    if ratio < 1.5: return None

    fmt = lambda x: round(x, 0) if is_kr else round(x, 2)
    return {
        'entry': fmt(close), 'stop_loss': fmt(stop), 'take_profit': fmt(tp),
        'risk': fmt(risk), 'reward': fmt(reward),
        'ratio': round(ratio, 2),
        'risk_pct':   round((stop  - close) / close * 100, 1),
        'reward_pct': round((tp - close) / close * 100, 1),
    }


# ─── Single-ticker analysis ───────────────────────────────────────────────────

def analyze(info: dict, is_kr: bool, min_avg_vol: float, min_price: float) -> dict | None:
    ticker = info['ticker']
    try:
        raw = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if raw is None or len(raw) < 130: return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw[['Open','High','Low','Close','Volume']].dropna()
        if len(df) < 130: return None

        close_last = float(df['Close'].iloc[-1])
        avg_vol_20 = float(df['Volume'].iloc[-21:-1].mean())  # 오늘 제외

        # ── 필터 ──────────────────────────────────────────────────────────────
        if avg_vol_20 < min_avg_vol:  return None   # 유동성 최소 기준
        if close_last < min_price:    return None   # 페니스탁 제외
        # 데이터 이상치 제거 (거래량 0 연속)
        if df['Volume'].tail(5).eq(0).sum() >= 3:   return None

        ind = compute_indicators(df)
        if ind is None: return None

        sr = score_stock(df, ind)
        if sr is None: return None

        rr = calc_risk_reward(df, ind, is_kr)
        if rr is None: return None

        prev_close = float(df['Close'].iloc[-2])
        change_pct = (close_last - prev_close) / prev_close * 100

        def fv(k): return float(ind[k].iloc[-1])
        rsi_v  = fv('rsi'); adx_v  = fv('adx')
        macd_v = fv('macd'); msig_v = fv('macd_sig')
        bb_u   = fv('bb_u'); bb_l   = fv('bb_l')
        bb_pos = min(max((close_last - bb_l) / (bb_u - bb_l + 1e-10), 0), 1)
        vol_ratio = float(df['Volume'].iloc[-1]) / (avg_vol_20 + 1)

        ma200 = fv('ma200')
        checklist = {
            'above_ma200':         bool(close_last > ma200 and ma200 > 0),
            'golden_cross_recent': bool(sr['breakdown']['golden_cross'] >= 10),
            'volume_surge':        bool(vol_ratio >= 2.0),
            'rsi_healthy':         bool(30 <= rsi_v <= 70),
            'macd_bullish':        bool(macd_v > msig_v),
            'trend_strong':        bool(sr['breakdown']['trend'] >= 15),
            'rr_ratio_good':       bool(rr['ratio'] >= 2.0),
        }

        price_fmt = round(close_last, 0) if is_kr else round(close_last, 2)
        return {
            'ticker':    ticker,
            'name':      info['name'],
            'market':    info['market'],
            'sector':    info.get('sector', 'Unknown'),
            'price':     price_fmt,
            'change_pct': round(change_pct, 1),
            'score':     sr['total'],
            'score_breakdown': sr['breakdown'],
            'signals':   sr['signals'],
            'technicals': {
                'rsi_14':      round(rsi_v,  1),
                'macd':        round(macd_v, 4),
                'macd_signal': round(msig_v, 4),
                'adx':         round(adx_v,  1),
                'volume_ratio': round(vol_ratio, 1),
                'bb_position': round(bb_pos, 2),
            },
            'risk_reward': rr,
            'price_history_30d': [round(float(p),2) for p in df['Close'].tail(30)],
            'ma_20': round(fv('ma20'), 2),
            'ma_60': round(fv('ma60'), 2),
            'checklist': checklist,
        }
    except Exception:
        return None


# ─── Universe builders ─────────────────────────────────────────────────────────

def get_kr_universe() -> list[dict]:
    """코스피+코스닥 전 종목 (시총 필터 없음, 거래량 기준만 적용)"""
    try:
        import FinanceDataReader as fdr
        results = []
        for market, sfx in [('KOSPI','KS'),('KOSDAQ','KQ')]:
            lst = fdr.StockListing(market)
            for _, row in lst.iterrows():
                code   = str(row.get('Code', row.get('Symbol',''))).zfill(6)
                name   = str(row.get('Name',''))
                sector = str(row.get('Sector', row.get('Industry','기타')))
                if code and name:
                    results.append({'ticker':f'{code}.{sfx}','name':name,'market':market,'sector':sector})
        print(f"  KR 유니버스: {len(results)}개")
        return results
    except Exception as e:
        print(f"  FinanceDataReader 실패({e}), fallback 사용")
        return KR_FALLBACK

def get_us_universe() -> list[dict]:
    """S&P 500 (Wikipedia) + 소형/성장주 확장 목록"""
    tickers = []
    # S&P 500
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        df  = pd.read_html(requests.get(url, timeout=15).text)[0]
        for _, row in df.iterrows():
            sym  = str(row.get('Symbol', row.get('Ticker symbol',''))).replace('.','-')
            name = str(row.get('Security', row.get('Company','')))
            sec  = str(row.get('GICS Sector','Unknown'))
            if sym: tickers.append({'ticker':sym,'name':name,'market':'NYSE/NASDAQ','sector':sec})
        print(f"  S&P 500: {len(tickers)}개")
    except Exception as e:
        print(f"  Wikipedia 파싱 실패({e})")
        tickers = list(US_LARGE_CAP)

    # 소형/성장주 확장 (거래량 기준으로만 필터)
    existing = {t['ticker'] for t in tickers}
    for t in US_GROWTH_EXTENDED:
        if t['ticker'] not in existing:
            tickers.append(t)

    print(f"  US 전체 유니버스: {len(tickers)}개 (S&P500 + 성장주)")
    return tickers


# ─── Universe lists ────────────────────────────────────────────────────────────

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
    {'ticker':'336260.KQ','name':'두산퓨얼셀','market':'KOSDAQ','sector':'수소에너지'},
    {'ticker':'950130.KQ','name':'엑스플로어','market':'KOSDAQ','sector':'방산'},
    {'ticker':'032350.KQ','name':'롯데관광개발','market':'KOSDAQ','sector':'여행/리조트'},
    {'ticker':'131970.KQ','name':'두산테스나','market':'KOSDAQ','sector':'반도체'},
    {'ticker':'067310.KQ','name':'하나마이크론','market':'KOSDAQ','sector':'반도체'},
]

US_LARGE_CAP = [
    {'ticker':'AAPL','name':'Apple','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MSFT','name':'Microsoft','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NVDA','name':'NVIDIA','market':'NASDAQ','sector':'Technology'},
    {'ticker':'GOOGL','name':'Alphabet','market':'NASDAQ','sector':'Technology'},
    {'ticker':'AMZN','name':'Amazon','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'META','name':'Meta Platforms','market':'NASDAQ','sector':'Technology'},
    {'ticker':'TSLA','name':'Tesla','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'JPM','name':'JPMorgan Chase','market':'NYSE','sector':'Financials'},
    {'ticker':'V','name':'Visa','market':'NYSE','sector':'Financials'},
    {'ticker':'WMT','name':'Walmart','market':'NYSE','sector':'Consumer Staples'},
]

# 소형/중형/성장주 확장 목록 (거래량 기준으로만 필터)
US_GROWTH_EXTENDED = [
    # AI / Data
    {'ticker':'PLTR','name':'Palantir','market':'NYSE','sector':'Technology'},
    {'ticker':'AI','name':'C3.ai','market':'NYSE','sector':'Technology'},
    {'ticker':'BBAI','name':'BigBear.ai','market':'NYSE','sector':'Technology'},
    {'ticker':'SOUN','name':'SoundHound AI','market':'NASDAQ','sector':'Technology'},
    {'ticker':'IREN','name':'Iris Energy','market':'NASDAQ','sector':'Technology'},
    {'ticker':'SMCI','name':'Super Micro Computer','market':'NASDAQ','sector':'Technology'},
    {'ticker':'ARM','name':'Arm Holdings','market':'NASDAQ','sector':'Technology'},
    # Crypto / Bitcoin
    {'ticker':'MSTR','name':'MicroStrategy','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MARA','name':'Marathon Digital','market':'NASDAQ','sector':'Technology'},
    {'ticker':'RIOT','name':'Riot Platforms','market':'NASDAQ','sector':'Technology'},
    {'ticker':'COIN','name':'Coinbase','market':'NASDAQ','sector':'Financials'},
    {'ticker':'CLSK','name':'CleanSpark','market':'NASDAQ','sector':'Technology'},
    {'ticker':'HUT','name':'Hut 8 Corp','market':'NASDAQ','sector':'Technology'},
    {'ticker':'BTBT','name':'Bit Digital','market':'NASDAQ','sector':'Technology'},
    # EV / Clean Energy
    {'ticker':'RIVN','name':'Rivian','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'LCID','name':'Lucid Group','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'NKLA','name':'Nikola','market':'NASDAQ','sector':'Industrials'},
    {'ticker':'PLUG','name':'Plug Power','market':'NASDAQ','sector':'Energy'},
    {'ticker':'FCEL','name':'FuelCell Energy','market':'NASDAQ','sector':'Energy'},
    {'ticker':'CHPT','name':'ChargePoint','market':'NYSE','sector':'Industrials'},
    # Space / Defense
    {'ticker':'RKLB','name':'Rocket Lab','market':'NASDAQ','sector':'Industrials'},
    {'ticker':'ASTS','name':'AST SpaceMobile','market':'NASDAQ','sector':'Communication'},
    {'ticker':'JOBY','name':'Joby Aviation','market':'NYSE','sector':'Industrials'},
    {'ticker':'ACHR','name':'Archer Aviation','market':'NYSE','sector':'Industrials'},
    {'ticker':'LUNR','name':'Intuitive Machines','market':'NASDAQ','sector':'Industrials'},
    # Biotech / Healthcare
    {'ticker':'MRNA','name':'Moderna','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'NVAX','name':'Novavax','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'RXRX','name':'Recursion Pharma','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'BEAM','name':'Beam Therapeutics','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'EDIT','name':'Editas Medicine','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'CRSP','name':'CRISPR Therapeutics','market':'NASDAQ','sector':'Health Care'},
    {'ticker':'NTLA','name':'Intellia Therapeutics','market':'NASDAQ','sector':'Health Care'},
    # Fintech / Payments
    {'ticker':'AFRM','name':'Affirm','market':'NASDAQ','sector':'Financials'},
    {'ticker':'HOOD','name':'Robinhood','market':'NASDAQ','sector':'Financials'},
    {'ticker':'SQ','name':'Block','market':'NYSE','sector':'Financials'},
    {'ticker':'SOFI','name':'SoFi Technologies','market':'NASDAQ','sector':'Financials'},
    {'ticker':'UPST','name':'Upstart','market':'NASDAQ','sector':'Financials'},
    # Cloud / SaaS
    {'ticker':'SNOW','name':'Snowflake','market':'NYSE','sector':'Technology'},
    {'ticker':'DDOG','name':'Datadog','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NET','name':'Cloudflare','market':'NYSE','sector':'Technology'},
    {'ticker':'CRWD','name':'CrowdStrike','market':'NASDAQ','sector':'Technology'},
    {'ticker':'ZS','name':'Zscaler','market':'NASDAQ','sector':'Technology'},
    {'ticker':'PANW','name':'Palo Alto Networks','market':'NASDAQ','sector':'Technology'},
    {'ticker':'GTLB','name':'GitLab','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MDB','name':'MongoDB','market':'NASDAQ','sector':'Technology'},
    {'ticker':'NOW','name':'ServiceNow','market':'NYSE','sector':'Technology'},
    {'ticker':'HUBS','name':'HubSpot','market':'NYSE','sector':'Technology'},
    # Semiconductors
    {'ticker':'AMD','name':'AMD','market':'NASDAQ','sector':'Technology'},
    {'ticker':'MU','name':'Micron Technology','market':'NASDAQ','sector':'Technology'},
    {'ticker':'ON','name':'ON Semiconductor','market':'NASDAQ','sector':'Technology'},
    {'ticker':'WOLF','name':'Wolfspeed','market':'NYSE','sector':'Technology'},
    {'ticker':'AMAT','name':'Applied Materials','market':'NASDAQ','sector':'Technology'},
    {'ticker':'LRCX','name':'Lam Research','market':'NASDAQ','sector':'Technology'},
    {'ticker':'TSM','name':'TSMC ADR','market':'NYSE','sector':'Technology'},
    {'ticker':'ASML','name':'ASML','market':'NASDAQ','sector':'Technology'},
    # Consumer / Retail
    {'ticker':'SHOP','name':'Shopify','market':'NYSE','sector':'Technology'},
    {'ticker':'ABNB','name':'Airbnb','market':'NASDAQ','sector':'Consumer Discretionary'},
    {'ticker':'DASH','name':'DoorDash','market':'NYSE','sector':'Consumer Discretionary'},
    {'ticker':'UBER','name':'Uber','market':'NYSE','sector':'Industrials'},
    {'ticker':'LYFT','name':'Lyft','market':'NASDAQ','sector':'Industrials'},
    # Meme / High-retail
    {'ticker':'GME','name':'GameStop','market':'NYSE','sector':'Consumer Discretionary'},
    {'ticker':'AMC','name':'AMC Entertainment','market':'NYSE','sector':'Communication'},
    # Commodities
    {'ticker':'MP','name':'MP Materials','market':'NYSE','sector':'Materials'},
    {'ticker':'UUUU','name':'Energy Fuels','market':'NYSE','sector':'Energy'},
    {'ticker':'GOLD','name':'Barrick Gold','market':'NYSE','sector':'Materials'},
    {'ticker':'NEM','name':'Newmont','market':'NYSE','sector':'Materials'},
    {'ticker':'FCX','name':'Freeport-McMoRan','market':'NYSE','sector':'Materials'},
]

# Test universes (각 시장 40종목)
KR_TEST = KR_FALLBACK  # 40종목
US_TEST = (US_LARGE_CAP +
           [t for t in US_GROWTH_EXTENDED
            if t['ticker'] in {'PLTR','MSTR','MARA','RIOT','COIN','RIVN','RKLB','ASTS',
                                'MRNA','AFRM','HOOD','SOFI','SNOW','DDOG','CRWD','SOUN',
                                'AMD','MU','SMCI','SHOP','UBER','GME','NVAX','NET','BBAI',
                                'IREN','CLSK','HUT','JOBY','ACHR'}])


# ─── Market summary ───────────────────────────────────────────────────────────

def get_market_summary() -> dict:
    syms = {'kospi':'^KS11','kosdaq':'^KQ11','sp500':'^GSPC','nasdaq':'^IXIC'}
    result = {}
    for key, sym in syms.items():
        try:
            d = yf.download(sym, period='5d', progress=False, auto_adjust=True)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            if d is not None and len(d) >= 2:
                curr = float(d['Close'].iloc[-1])
                prev = float(d['Close'].iloc[-2])
                result[key] = {'index': round(curr,2), 'change_pct': round((curr-prev)/prev*100,2)}
            else:
                result[key] = {'index':0,'change_pct':0}
        except:
            result[key] = {'index':0,'change_pct':0}
        time.sleep(0.2)
    return result


# ─── JSON serializer ──────────────────────────────────────────────────────────

def _default(obj):
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    if isinstance(obj, np.bool_):    return bool(obj)
    raise TypeError(f'{type(obj)} not serializable')


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test',    action='store_true', help='각 시장 ~40종목 빠른 테스트')
    ap.add_argument('--kr-only', action='store_true')
    ap.add_argument('--us-only', action='store_true')
    args = ap.parse_args()

    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    print(f"\n{'='*65}")
    print(f" Signal Deck Screener  {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f" MODE: {'TEST' if args.test else 'FULL'}")
    print(f"{'='*65}\n")

    print("📊 시장 지수 수집...")
    mkt = get_market_summary()
    for k,v in mkt.items():
        print(f"  {k.upper():8s}  {v['index']:>10,.2f}  ({v['change_pct']:+.2f}%)")

    results = {'kr':[], 'us':[]}

    # ── 한국 ──────────────────────────────────────────────────────────────────
    if not args.us_only:
        print("\n🇰🇷  한국 종목 스캔...")
        print("  필터: 20일 평균 거래량 5만주 이상, 주가 1000원 이상 (시총 제한 없음)")
        kr_list = KR_TEST if args.test else get_kr_universe()
        kr_cands, passed = [], 0
        for i, info in enumerate(kr_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(kr_list)}] {info['ticker']:<14} {info['name']:<12}")
            sys.stdout.flush()
            r = analyze(info, is_kr=True, min_avg_vol=50_000, min_price=1_000)
            if r:
                passed += 1
                kr_cands.append(r)
                sys.stdout.write(
                    f"  ✅ score={r['score']:3d}  "
                    f"vol={r['technicals']['volume_ratio']:.1f}x  "
                    f"R:R={r['risk_reward']['ratio']:.2f}"
                )
            time.sleep(0.35)
        print(f"\n  통과: {passed}/{len(kr_list)}종목")
        kr_top = sorted(kr_cands, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(kr_top): s['rank'] = i + 1
        results['kr'] = kr_top
        print(f"  KR TOP10: {[s['name'] for s in kr_top]}")

    # ── 미국 ──────────────────────────────────────────────────────────────────
    if not args.kr_only:
        print("\n🇺🇸  미국 종목 스캔...")
        print("  필터: 20일 평균 거래량 10만주 이상, 주가 $1 이상 (시총 제한 없음)")
        us_list = US_TEST if args.test else get_us_universe()
        us_cands, passed = [], 0
        for i, info in enumerate(us_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(us_list)}] {info['ticker']:<8} {info['name']:<20}")
            sys.stdout.flush()
            r = analyze(info, is_kr=False, min_avg_vol=100_000, min_price=1.0)
            if r:
                passed += 1
                us_cands.append(r)
                sys.stdout.write(
                    f"  ✅ score={r['score']:3d}  "
                    f"vol={r['technicals']['volume_ratio']:.1f}x  "
                    f"R:R={r['risk_reward']['ratio']:.2f}"
                )
            time.sleep(0.35)
        print(f"\n  통과: {passed}/{len(us_list)}종목")
        us_top = sorted(us_cands, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(us_top): s['rank'] = i + 1
        results['us'] = us_top
        print(f"  US TOP10: {[s['ticker'] for s in us_top]}")

    # ── 저장 ──────────────────────────────────────────────────────────────────
    output = {'updated_at': now.isoformat(), 'market_summary': mkt,
              'screening_results': results}
    out_dir = Path(__file__).parent.parent / 'public' / 'data'
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in [out_dir / 'latest.json', out_dir / f'{now.strftime("%Y-%m-%d")}.json']:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=_default)
    print(f"\n✅ 저장: {out_dir}/latest.json")

    for old in sorted(out_dir.glob('????-??-??.json'))[:-7]:
        old.unlink()

    print(f"🎉 완료!  KR {len(results['kr'])}개 + US {len(results['us'])}개\n")


if __name__ == '__main__':
    main()
