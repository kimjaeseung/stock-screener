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
from datetime import datetime, timezone, timedelta, date as dt_date
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
    tr   = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
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
    return {
        'ma5':  _sma(c, 5),  'ma20': _sma(c, 20), 'ma60': _sma(c, 60),
        'ma120': _sma(c, 120), 'ma200': _sma(c, 200),
        'macd': macd_line, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
        'rsi':  _rsi(c, 14),
        'bb_u': bb_u, 'bb_m': bb_m, 'bb_l': bb_l,
        'atr':  _atr(h, l, c, 14),
        'adx':  _adx(h, l, c, 14),
        'stoch_k': stoch_k, 'stoch_d': stoch_d,
        'volume': v,
    }


# ─── Scoring (기본 100점 만점 + R:R 보너스 최대 5점) ──────────────────────────
# 배점: trend 25 / golden_cross 20 / momentum 20 / volume 20 / support 10 / bollinger 10

def detect_chart_patterns(df: pd.DataFrame) -> tuple[int, list[str]]:
    """유명 차트 패턴 감지 → (보너스 점수, 시그널 목록)"""
    c = df['Close'].values
    h = df['High'].values
    l_arr = df['Low'].values
    n = len(c)
    if n < 60:
        return 0, []

    bonus = 0
    patterns_found = []

    def local_minima(arr, order=3):
        result = []
        for i in range(order, len(arr) - order):
            if arr[i] == min(arr[i-order:i+order+1]):
                result.append((i, arr[i]))
        return result

    def local_maxima(arr, order=3):
        result = []
        for i in range(order, len(arr) - order):
            if arr[i] == max(arr[i-order:i+order+1]):
                result.append((i, arr[i]))
        return result

    # ── 1. 컵앤핸들 (Cup & Handle) — 최대 15점 ──────────────────────────────
    try:
        # 50일 컵 구간 + 최근 10일 핸들
        if n >= 65:
            cup = c[-65:-10]
            handle = c[-10:]
            cup_left_high = cup[:20].max()
            cup_low = cup[10:40].min()
            cup_right_high = cup[35:].max()
            handle_low = handle.min()
            handle_high = handle.max()
            cur = c[-1]

            cup_depth = (cup_left_high - cup_low) / (cup_left_high + 1e-10)
            recovery = (cup_right_high - cup_low) / (cup_left_high - cup_low + 1e-10)
            handle_drop = (cup_right_high - handle_low) / (cup_right_high + 1e-10)

            if (0.12 <= cup_depth <= 0.55
                    and recovery >= 0.80
                    and 0.02 <= handle_drop <= 0.20
                    and cur >= handle_high * 0.97):
                bonus += 15
                patterns_found.append('컵앤핸들 패턴 🏆')
    except Exception:
        pass

    # ── 2. 더블바텀 (Double Bottom) — 최대 12점 ────────────────────────────
    try:
        p60 = c[-60:]
        lows = local_minima(p60, order=4)
        if len(lows) >= 2:
            low1, low2 = lows[-2], lows[-1]
            gap = low2[0] - low1[0]
            price_diff = abs(low1[1] - low2[1]) / (low1[1] + 1e-10)
            if gap >= 12 and price_diff <= 0.06:
                seg = p60[low1[0]:low2[0]+1]
                neckline = seg.max() if len(seg) > 0 else 0
                cur = p60[-1]
                if neckline > 0 and cur >= neckline * 0.96:
                    bonus += 12
                    patterns_found.append('더블바텀 패턴 🔄')
    except Exception:
        pass

    # ── 3. 역헤드앤숄더 (Inverse H&S) — 최대 12점 ─────────────────────────
    try:
        p60 = c[-60:]
        lows = local_minima(p60, order=4)
        if len(lows) >= 3:
            ls, hd, rs = lows[-3], lows[-2], lows[-1]
            # 헤드가 가장 낮고, 양 어깨가 비슷한 높이
            if hd[1] < ls[1] and hd[1] < rs[1]:
                shoulder_sym = abs(ls[1] - rs[1]) / (ls[1] + 1e-10)
                if shoulder_sym <= 0.08:
                    seg1 = p60[ls[0]:hd[0]+1] if hd[0] > ls[0] else np.array([0])
                    seg2 = p60[hd[0]:rs[0]+1] if rs[0] > hd[0] else np.array([0])
                    neckline = max(seg1.max(), seg2.max())
                    cur = p60[-1]
                    if cur >= neckline * 0.97:
                        bonus += 12
                        patterns_found.append('역헤드앤숄더 🎯')
    except Exception:
        pass

    # ── 4. 불플래그 (Bull Flag) — 최대 10점 ──────────────────────────────────
    try:
        if n >= 30:
            p30 = c[-30:]
            pole_gain = (p30[9] - p30[0]) / (p30[0] + 1e-10)
            flag = p30[9:]
            flag_range = (flag.max() - flag.min()) / (flag.max() + 1e-10)
            flag_slope = (flag[-1] - flag[0]) / (flag[0] + 1e-10)
            cur = c[-1]
            if (pole_gain >= 0.07
                    and 0.02 <= flag_range <= 0.18
                    and -0.12 <= flag_slope <= 0.03
                    and cur >= flag.max() * 0.97):
                bonus += 10
                patterns_found.append('불플래그 패턴 🚩')
    except Exception:
        pass

    # ── 5. VCP (변동성 수축 패턴) — 최대 8점 ────────────────────────────────
    try:
        if n >= 60:
            segs = [c[-60:-45], c[-45:-30], c[-30:-15], c[-15:]]
            ranges = [(s.max()-s.min())/(s.mean()+1e-10) for s in segs if len(s) > 0]
            if len(ranges) == 4:
                contracting = all(ranges[i] > ranges[i+1] * 0.9 for i in range(3))
                if contracting and ranges[-1] < 0.06:
                    bonus += 8
                    patterns_found.append('변동성 수축 (VCP) 📐')
    except Exception:
        pass

    # ── 6. 상승삼각형 (Ascending Triangle) — 최대 8점 ───────────────────────
    try:
        if n >= 30:
            h30 = h[-30:]
            l30 = l_arr[-30:]
            top_highs = sorted(h30)[-6:]
            resistance_std = float(np.std(top_highs)) / (float(np.mean(top_highs)) + 1e-10)
            lows_early = l30[:10].min()
            lows_mid   = l30[10:20].min()
            lows_late  = l30[20:].min()
            rising_support = lows_late > lows_mid > lows_early * 0.99
            resistance = float(np.mean(top_highs))
            cur = c[-1]
            if resistance_std < 0.025 and rising_support and cur >= resistance * 0.97:
                bonus += 8
                patterns_found.append('상승삼각형 패턴 △')
    except Exception:
        pass

    return min(bonus, 20), patterns_found


def score_stock(df: pd.DataFrame, ind: dict) -> dict | None:
    close = float(df['Close'].iloc[-1])
    prev  = float(df['Close'].iloc[-2])

    v_ser = ind['volume']
    vol_current  = float(v_ser.iloc[-1])           # 가장 최근 완료된 거래일
    vol_20d_avg  = float(v_ser.iloc[-21:-1].mean()) # 직전 20일 평균 (최근 제외)
    vol_5d_avg   = float(v_ser.iloc[-5:].mean())    # 최근 5일 평균
    vol_ratio    = vol_current / (vol_20d_avg + 1)

    def v(k):  return float(ind[k].iloc[-1])
    def vp(k): return float(ind[k].iloc[-2])

    ma5  = v('ma5');  ma20 = v('ma20'); ma60 = v('ma60')
    ma120 = v('ma120'); ma200 = v('ma200')
    rsi  = v('rsi');  adx  = v('adx')
    macd = v('macd'); msig = v('macd_sig')
    mhist = v('macd_hist'); mhist_prev = vp('macd_hist')
    bb_u = v('bb_u'); bb_m = v('bb_m'); bb_l = v('bb_l')
    stk  = v('stoch_k'); std_ = v('stoch_d')
    stk_prev = vp('stoch_k'); std_prev = vp('stoch_d')

    if any(np.isnan(x) for x in [ma5, ma20, ma60, ma120, ma200, rsi, adx, macd, bb_u]):
        return None

    bd = {'trend': 0, 'golden_cross': 0, 'momentum': 0, 'volume': 0, 'support': 0, 'bollinger': 0}
    signals = []

    # ── 1. 추세 (25점) ────────────────────────────────────────────────────────
    # 단기 정배열: 종가 > 5일선 > 20일선 > 60일선
    if close > ma5 > ma20 > ma60:
        bd['trend'] += 10; signals.append('이평선 정배열 (종가>5>20>60) 🟢')
    elif close > ma20 > ma60:
        bd['trend'] += 5; signals.append('중기 정배열 (종가>20>60)')

    # 중기 정배열: 20일선 > 60일선 > 120일선
    if ma20 > ma60 > ma120:
        bd['trend'] += 5; signals.append('중장기 정배열 (20>60>120)')

    # 200일선 위
    if close > ma200:
        bd['trend'] += 5; signals.append('200일선 위')

    # 20일선 기울기 (최근 5일간 상승 여부)
    ma20_5ago = float(ind['ma20'].iloc[-6]) if len(ind['ma20'].dropna()) >= 6 else ma20
    if ma20 > ma20_5ago * 1.001:
        bd['trend'] += 3; signals.append('20일선 우상향 중')

    # ADX 추세 강도
    if adx > 25:
        bd['trend'] += 2; signals.append(f'ADX {adx:.0f} — 추세 강함')

    bd['trend'] = min(bd['trend'], 25)

    # ── 2. 골든크로스 / 크로스오버 감지 (20점) ───────────────────────────────
    gc = 0

    # 5일선 × 20일선 골든크로스 (최근 5거래일 이내)
    for i in range(1, 6):
        try:
            if (float(ind['ma5'].iloc[-i-1]) < float(ind['ma20'].iloc[-i-1]) and
                    float(ind['ma5'].iloc[-i]) >= float(ind['ma20'].iloc[-i])):
                gc = max(gc, 10); signals.append('5일×20일 골든크로스 ✨'); break
        except Exception:
            pass

    # 20일선 × 60일선 골든크로스 (최근 10거래일 이내)
    for i in range(1, 11):
        try:
            if (float(ind['ma20'].iloc[-i-1]) < float(ind['ma60'].iloc[-i-1]) and
                    float(ind['ma20'].iloc[-i]) >= float(ind['ma60'].iloc[-i])):
                gc = max(gc, 10); signals.append('20일×60일 골든크로스 ✨'); break
        except Exception:
            pass

    # MACD 골든크로스 (최근 5거래일 이내)
    for i in range(1, 6):
        try:
            if (float(ind['macd'].iloc[-i-1]) < float(ind['macd_sig'].iloc[-i-1]) and
                    float(ind['macd'].iloc[-i]) >= float(ind['macd_sig'].iloc[-i])):
                gc = max(gc, 10); signals.append('MACD 골든크로스 ✨'); break
        except Exception:
            pass

    # MACD > Signal (약한 신호, 최대 5점)
    if macd > msig and gc < 10:
        gc = max(gc, 5); signals.append('MACD > Signal (상승 추세)')

    bd['golden_cross'] = min(gc, 20)

    # ── 3. 모멘텀 & 오실레이터 (20점) ─────────────────────────────────────────
    # RSI 구간별 차등 점수
    if 30 <= rsi <= 40:
        bd['momentum'] += 8; signals.append(f'RSI {rsi:.0f} — 과매도 탈출 직전 🎯')
    elif 40 < rsi <= 60:
        bd['momentum'] += 5; signals.append(f'RSI {rsi:.0f} (건강한 구간)')
    elif rsi < 30:
        bd['momentum'] += 3; signals.append(f'RSI {rsi:.0f} — 과매도 (반등 가능)')
    elif 60 < rsi <= 70:
        bd['momentum'] += 3  # 상승 추세 중이지만 다소 과열

    # MACD 히스토그램 방향성
    if mhist > 0 and mhist > mhist_prev:
        bd['momentum'] += 5; signals.append('MACD 히스토그램 증가 ↑')
    elif mhist > 0:
        bd['momentum'] += 3

    # 스토캐스틱 %K 상향 돌파 (%K가 %D를 아래에서 위로 돌파)
    if not np.isnan(stk) and not np.isnan(std_):
        if stk_prev < std_prev and stk >= std_:
            bd['momentum'] += 5; signals.append(f'스토캐스틱 상향 돌파 ({stk:.0f}%)')
        elif stk > std_ and stk < 80:
            bd['momentum'] += 2  # 이미 돌파 상태

    # MACD > Signal 보조
    if macd > msig:
        bd['momentum'] += 2

    bd['momentum'] = min(bd['momentum'], 20)

    # ── 4. 거래량 (20점) ──────────────────────────────────────────────────────
    if vol_ratio >= 3.0:
        bd['volume'] += 20; signals.append(f'거래량 {vol_ratio:.1f}배 폭발 🔥')
    elif vol_ratio >= 2.0:
        bd['volume'] += 15; signals.append(f'거래량 {vol_ratio:.1f}배 급증 📈')
    elif vol_ratio >= 1.5:
        bd['volume'] += 10; signals.append(f'거래량 {vol_ratio:.1f}배 증가')
    elif vol_ratio >= 1.2:
        bd['volume'] += 5

    # 최근 5일 거래량 트렌드 상승
    if vol_5d_avg > vol_20d_avg * 1.3:
        bd['volume'] = min(bd['volume'] + 5, 20)
        if not any('거래량' in s for s in signals):
            signals.append('거래량 트렌드 증가 (5일 > 20일 ×1.3)')

    bd['volume'] = min(bd['volume'], 20)

    # ── 5. 지지/저항 & 피보나치 (10점) ────────────────────────────────────────
    hi60 = float(df['High'].tail(60).max())
    lo60 = float(df['Low'].tail(60).min())
    diff = hi60 - lo60
    if diff > 0:
        f382 = hi60 - diff * 0.382
        f618 = hi60 - diff * 0.618
        if f618 <= close <= f382:
            bd['support'] += 5; signals.append('피보나치 38.2~61.8% 지지 구간')

    # 이평선 근처 지지 (±2%)
    if abs(close - ma20) / (ma20 + 1e-10) < 0.02:
        bd['support'] += 3; signals.append('20일선 근처 지지')
    elif abs(close - ma60) / (ma60 + 1e-10) < 0.02:
        bd['support'] += 3; signals.append('60일선 근처 지지')

    # 볼린저 하단 반등
    if not np.isnan(bb_l) and close > bb_l and float(df['Low'].tail(5).min()) <= bb_l * 1.01:
        bd['support'] += 5; signals.append('볼린저 하단 반등')

    bd['support'] = min(bd['support'], 10)

    # ── 6. 볼린저 스퀴즈 & 돌파 (10점) ───────────────────────────────────────
    bw = (ind['bb_u'] - ind['bb_l']).dropna()
    if len(bw) >= 20:
        tail = bw.tail(120)
        pct = (tail < float(bw.iloc[-1])).sum() / len(tail)
        if pct <= 0.30:
            bd['bollinger'] += 5; signals.append(f'볼린저 스퀴즈 (폭 하위 {pct*100:.0f}%)')
            # 스퀴즈 후 상단 돌파
            if close > float(ind['bb_u'].iloc[-1]) and prev <= float(ind['bb_u'].iloc[-2]):
                bd['bollinger'] += 5; signals.append('스퀴즈 후 상단 돌파 🚀')
        elif close > bb_u:
            bd['bollinger'] += 5; signals.append('볼린저 상단 돌파')

    bd['bollinger'] = min(bd['bollinger'], 10)

    # ── 차트 패턴 보너스 ──────────────────────────────────────────────────────
    pattern_bonus, pattern_sigs = detect_chart_patterns(df)
    total = sum(bd.values()) + pattern_bonus
    signals = (pattern_sigs + signals)[:6]  # 패턴 시그널 앞에 배치

    return {
        'total':     total,
        'breakdown': bd,
        'signals':   signals,
        'vol_ratio': vol_ratio,
    }


# ─── Risk/Reward ──────────────────────────────────────────────────────────────

def calc_risk_reward(df: pd.DataFrame, ind: dict, is_kr: bool) -> dict | None:
    close = float(df['Close'].iloc[-1])
    atr   = float(ind['atr'].iloc[-1])
    bb_u  = float(ind['bb_u'].iloc[-1])
    lo20  = float(df['Low'].tail(20).min())

    # 손절: max(현재가 - 2*ATR, 최근 20일 최저가)
    stops = [close - 2.0 * atr, lo20]
    valid_stops = [s for s in stops if 0 < s < close * 0.97]
    if not valid_stops:
        return None
    stop = max(valid_stops)

    # 목표: min(최근 60일 최고가, 볼린저 상단)
    hi60 = float(df['High'].tail(60).max())
    tgts = [hi60, bb_u * 1.01]
    valid_tgts = [t for t in tgts if t > close * 1.02]
    if not valid_tgts:
        return None
    tp = min(valid_tgts)

    risk   = close - stop
    reward = tp - close
    if risk <= 0:
        return None
    ratio = reward / risk
    if ratio < 1.5:  # 1.5:1 이상 (기존 2:1에서 완화)
        return None

    fmt = lambda x: round(x, 0) if is_kr else round(x, 2)
    return {
        'entry':      fmt(close),
        'stop_loss':  fmt(stop),
        'take_profit': fmt(tp),
        'risk':       fmt(risk),
        'reward':     fmt(reward),
        'ratio':      round(ratio, 2),
        'risk_pct':   round((stop - close) / close * 100, 1),
        'reward_pct': round((tp - close) / close * 100, 1),
    }


# ─── Single-ticker analysis ───────────────────────────────────────────────────

def analyze(info: dict, is_kr: bool, min_avg_vol: float, min_price: float) -> dict | None:
    ticker = info['ticker']
    try:
        raw = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
        if raw is None or len(raw) < 130:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        if len(df) < 130:
            return None

        # ── 당일 미완료 데이터 제거 ────────────────────────────────────────────
        # yfinance가 장중에 오늘 데이터를 partial로 포함할 수 있음.
        # 오늘 날짜와 마지막 행의 날짜가 같으면 제거 (완료된 거래일만 사용)
        today = dt_date.today()
        if len(df) > 0 and df.index[-1].date() == today:
            df = df.iloc[:-1]
        if len(df) < 130:
            return None

        close_last = float(df['Close'].iloc[-1])
        avg_vol_20 = float(df['Volume'].iloc[-21:-1].mean())  # 최근 완료일 제외 20일

        # 최소 거래대금 필터 (미세주 제외)
        daily_dollar_vol = avg_vol_20 * close_last
        if is_kr:
            if daily_dollar_vol < 5_000_000_000:  # ₩50억/일 이상
                return None
        else:
            if daily_dollar_vol < 5_000_000:  # $500만/일 이상
                return None

        # ── 필터 ──────────────────────────────────────────────────────────────
        if avg_vol_20 < min_avg_vol:
            return None
        if close_last < min_price:
            return None
        # 거래량 이상치 제거 (최근 5일 중 3일 이상 0)
        if df['Volume'].tail(5).eq(0).sum() >= 3:
            return None

        ind = compute_indicators(df)
        if ind is None:
            return None

        sr = score_stock(df, ind)
        if sr is None:
            return None

        rr = calc_risk_reward(df, ind, is_kr)
        if rr is None:
            return None

        # ── R:R 보너스 (최대 +5점) ────────────────────────────────────────────
        rr_bonus = 0
        if rr['ratio'] >= 3.0:
            rr_bonus = 5
        elif rr['ratio'] >= 2.0:
            rr_bonus = 3
        elif rr['ratio'] >= 1.5:
            rr_bonus = 1

        final_score = sr['total'] + rr_bonus

        prev_close  = float(df['Close'].iloc[-2])
        change_pct  = (close_last - prev_close) / prev_close * 100

        def fv(k): return float(ind[k].iloc[-1])
        rsi_v  = fv('rsi');  adx_v  = fv('adx')
        macd_v = fv('macd'); msig_v = fv('macd_sig')
        bb_u   = fv('bb_u'); bb_l   = fv('bb_l')
        bb_pos = min(max((close_last - bb_l) / (bb_u - bb_l + 1e-10), 0), 1)
        vol_ratio = sr['vol_ratio']
        ma200  = fv('ma200')

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
            'score':     final_score,
            'score_breakdown': sr['breakdown'],
            'signals':   sr['signals'],
            'technicals': {
                'rsi_14':       round(rsi_v, 1),
                'macd':         round(macd_v, 4),
                'macd_signal':  round(msig_v, 4),
                'adx':          round(adx_v, 1),
                'volume_ratio': round(vol_ratio, 2),
                'bb_position':  round(bb_pos, 2),
            },
            'risk_reward': rr,
            'price_history_30d': [round(float(p), 2) for p in df['Close'].tail(30)],
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
        for market, sfx in [('KOSPI', 'KS'), ('KOSDAQ', 'KQ')]:
            lst = fdr.StockListing(market)
            for _, row in lst.iterrows():
                code   = str(row.get('Code', row.get('Symbol', ''))).zfill(6)
                name   = str(row.get('Name', ''))
                sector = str(row.get('Sector', row.get('Industry', '기타')))
                if code and name:
                    results.append({'ticker': f'{code}.{sfx}', 'name': name, 'market': market, 'sector': sector})
        print(f"  KR 유니버스: {len(results)}개")
        return results
    except Exception as e:
        print(f"  FinanceDataReader 실패({e}), fallback 사용")
        return KR_FALLBACK


def get_us_universe() -> list[dict]:
    """NASDAQ API → S&P500 Wikipedia → 내장 목록 순으로 fallback"""
    tickers: list[dict] = []

    # 1순위: NASDAQ 공식 API (NASDAQ + NYSE 전체)
    for exchange in ['NASDAQ', 'NYSE']:
        try:
            url = (
                f'https://api.nasdaq.com/api/screener/stocks'
                f'?tableonly=true&limit=10000&exchange={exchange}&download=true'
            )
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; SignalDeck/1.0)'}
            resp = requests.get(url, headers=headers, timeout=20)
            data = resp.json()
            rows = data.get('data', {}).get('rows') or []
            before = len(tickers)
            existing = {t['ticker'] for t in tickers}
            for row in rows:
                sym  = str(row.get('symbol', '')).strip()
                name = str(row.get('name', '')).strip()
                sec  = str(row.get('sector', 'Unknown')).strip() or 'Unknown'
                if sym and sym not in existing:
                    tickers.append({'ticker': sym, 'name': name, 'market': exchange, 'sector': sec})
                    existing.add(sym)
            print(f"  {exchange}: {len(tickers)-before}개 추가")
        except Exception as e:
            print(f"  {exchange} API 실패({e})")

    # 2순위: S&P 500 Wikipedia (API 실패 시)
    if len(tickers) < 50:
        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            df  = pd.read_html(requests.get(url, timeout=15).text)[0]
            existing = {t['ticker'] for t in tickers}
            for _, row in df.iterrows():
                sym  = str(row.get('Symbol', row.get('Ticker symbol', ''))).replace('.', '-')
                name = str(row.get('Security', row.get('Company', '')))
                sec  = str(row.get('GICS Sector', 'Unknown'))
                if sym and sym not in existing:
                    tickers.append({'ticker': sym, 'name': name, 'market': 'NYSE/NASDAQ', 'sector': sec})
                    existing.add(sym)
            print(f"  S&P 500 fallback: {len(tickers)}개")
        except Exception as e:
            print(f"  S&P500 Wikipedia 실패({e})")

    # 3순위: 내장 목록
    if len(tickers) < 50:
        tickers = list(US_LARGE_CAP)

    # 성장주 추가 (누락된 경우)
    existing = {t['ticker'] for t in tickers}
    for t in US_GROWTH_EXTENDED:
        if t['ticker'] not in existing:
            tickers.append(t)
            existing.add(t['ticker'])

    print(f"  US 전체 유니버스: {len(tickers)}개")
    return tickers


# ─── Universe lists ────────────────────────────────────────────────────────────

KR_FALLBACK = [
    # KOSPI 대형주
    {'ticker': '005930.KS', 'name': '삼성전자',        'market': 'KOSPI', 'sector': '반도체'},
    {'ticker': '000660.KS', 'name': 'SK하이닉스',       'market': 'KOSPI', 'sector': '반도체'},
    {'ticker': '035420.KS', 'name': 'NAVER',           'market': 'KOSPI', 'sector': '인터넷'},
    {'ticker': '035720.KS', 'name': '카카오',           'market': 'KOSPI', 'sector': '인터넷'},
    {'ticker': '005380.KS', 'name': '현대차',           'market': 'KOSPI', 'sector': '자동차'},
    {'ticker': '000270.KS', 'name': '기아',             'market': 'KOSPI', 'sector': '자동차'},
    {'ticker': '051910.KS', 'name': 'LG화학',           'market': 'KOSPI', 'sector': '화학'},
    {'ticker': '006400.KS', 'name': '삼성SDI',          'market': 'KOSPI', 'sector': '2차전지'},
    {'ticker': '373220.KS', 'name': 'LG에너지솔루션',   'market': 'KOSPI', 'sector': '2차전지'},
    {'ticker': '207940.KS', 'name': '삼성바이오로직스', 'market': 'KOSPI', 'sector': '바이오'},
    {'ticker': '068270.KS', 'name': '셀트리온',         'market': 'KOSPI', 'sector': '바이오'},
    {'ticker': '003550.KS', 'name': 'LG',              'market': 'KOSPI', 'sector': '지주'},
    {'ticker': '012330.KS', 'name': '현대모비스',       'market': 'KOSPI', 'sector': '자동차부품'},
    {'ticker': '028260.KS', 'name': '삼성물산',         'market': 'KOSPI', 'sector': '건설'},
    {'ticker': '034730.KS', 'name': 'SK',              'market': 'KOSPI', 'sector': '지주'},
    {'ticker': '015760.KS', 'name': '한국전력',         'market': 'KOSPI', 'sector': '전기'},
    {'ticker': '003490.KS', 'name': '대한항공',         'market': 'KOSPI', 'sector': '항공'},
    {'ticker': '259960.KS', 'name': '크래프톤',         'market': 'KOSPI', 'sector': '게임'},
    {'ticker': '018260.KS', 'name': '삼성SDS',          'market': 'KOSPI', 'sector': 'IT서비스'},
    {'ticker': '009150.KS', 'name': '삼성전기',         'market': 'KOSPI', 'sector': '전기전자'},
    {'ticker': '000810.KS', 'name': '삼성화재',         'market': 'KOSPI', 'sector': '보험'},
    {'ticker': '096770.KS', 'name': 'SK이노베이션',     'market': 'KOSPI', 'sector': '에너지'},
    {'ticker': '011200.KS', 'name': 'HMM',             'market': 'KOSPI', 'sector': '해운'},
    {'ticker': '055550.KS', 'name': '신한지주',         'market': 'KOSPI', 'sector': '금융'},
    {'ticker': '105560.KS', 'name': 'KB금융',           'market': 'KOSPI', 'sector': '금융'},
    # KOSDAQ 성장주
    {'ticker': '086520.KQ', 'name': '에코프로',         'market': 'KOSDAQ', 'sector': '2차전지소재'},
    {'ticker': '247540.KQ', 'name': '에코프로비엠',     'market': 'KOSDAQ', 'sector': '2차전지소재'},
    {'ticker': '196170.KQ', 'name': '알테오젠',         'market': 'KOSDAQ', 'sector': '바이오'},
    {'ticker': '357780.KQ', 'name': '솔브레인',         'market': 'KOSDAQ', 'sector': '반도체소재'},
    {'ticker': '041510.KQ', 'name': 'SM엔터',           'market': 'KOSDAQ', 'sector': '엔터'},
    {'ticker': '035900.KQ', 'name': 'JYP Ent',         'market': 'KOSDAQ', 'sector': '엔터'},
    {'ticker': '293490.KQ', 'name': '카카오게임즈',     'market': 'KOSDAQ', 'sector': '게임'},
    {'ticker': '112040.KQ', 'name': '위메이드',         'market': 'KOSDAQ', 'sector': '게임'},
    {'ticker': '336260.KQ', 'name': '두산퓨얼셀',       'market': 'KOSDAQ', 'sector': '수소에너지'},
    {'ticker': '950130.KQ', 'name': '엑스플로어',       'market': 'KOSDAQ', 'sector': '방산'},
    {'ticker': '032350.KQ', 'name': '롯데관광개발',     'market': 'KOSDAQ', 'sector': '여행/리조트'},
    {'ticker': '131970.KQ', 'name': '두산테스나',       'market': 'KOSDAQ', 'sector': '반도체'},
    {'ticker': '067310.KQ', 'name': '하나마이크론',     'market': 'KOSDAQ', 'sector': '반도체'},
    {'ticker': '039030.KQ', 'name': '이오테크닉스',     'market': 'KOSDAQ', 'sector': '반도체장비'},
    {'ticker': '036830.KQ', 'name': '솔브레인홀딩스',   'market': 'KOSDAQ', 'sector': '반도체소재'},
    {'ticker': '137310.KQ', 'name': '에스디바이오센서', 'market': 'KOSDAQ', 'sector': '바이오'},
    {'ticker': '214150.KQ', 'name': '클래시스',         'market': 'KOSDAQ', 'sector': '의료기기'},
    {'ticker': '238490.KQ', 'name': '에이비엘바이오',   'market': 'KOSDAQ', 'sector': '바이오'},
    {'ticker': '145020.KQ', 'name': '휴젤',             'market': 'KOSDAQ', 'sector': '바이오'},
    {'ticker': '023160.KQ', 'name': '태광',             'market': 'KOSDAQ', 'sector': '방산'},
    {'ticker': '099440.KQ', 'name': '스맥',             'market': 'KOSDAQ', 'sector': '방산'},
    {'ticker': '079550.KQ', 'name': 'LIG넥스원',        'market': 'KOSPI', 'sector': '방산'},
    {'ticker': '012450.KS', 'name': '한화에어로스페이스', 'market': 'KOSPI', 'sector': '방산'},
    {'ticker': '329180.KS', 'name': 'HD현대중공업',     'market': 'KOSPI', 'sector': '조선'},
    {'ticker': '009540.KS', 'name': 'HD한국조선해양',   'market': 'KOSPI', 'sector': '조선'},
]

US_LARGE_CAP = [
    {'ticker': 'AAPL',  'name': 'Apple',           'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'MSFT',  'name': 'Microsoft',        'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'NVDA',  'name': 'NVIDIA',           'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'GOOGL', 'name': 'Alphabet',         'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'AMZN',  'name': 'Amazon',           'market': 'NASDAQ', 'sector': 'Consumer Discretionary'},
    {'ticker': 'META',  'name': 'Meta Platforms',   'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'TSLA',  'name': 'Tesla',            'market': 'NASDAQ', 'sector': 'Consumer Discretionary'},
    {'ticker': 'JPM',   'name': 'JPMorgan Chase',   'market': 'NYSE',   'sector': 'Financials'},
    {'ticker': 'V',     'name': 'Visa',             'market': 'NYSE',   'sector': 'Financials'},
    {'ticker': 'WMT',   'name': 'Walmart',          'market': 'NYSE',   'sector': 'Consumer Staples'},
]

# 소형/중형/성장주 확장 목록
US_GROWTH_EXTENDED = [
    # AI / Data
    {'ticker': 'PLTR',  'name': 'Palantir',             'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'AI',    'name': 'C3.ai',                'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'BBAI',  'name': 'BigBear.ai',           'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'SOUN',  'name': 'SoundHound AI',        'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'IREN',  'name': 'Iris Energy',          'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'SMCI',  'name': 'Super Micro Computer', 'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'ARM',   'name': 'Arm Holdings',         'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'IONQ',  'name': 'IonQ',                 'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'RGTI',  'name': 'Rigetti Computing',    'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'QUBT',  'name': 'Quantum Computing',    'market': 'NASDAQ', 'sector': 'Technology'},
    # Crypto / Bitcoin
    {'ticker': 'MSTR',  'name': 'MicroStrategy',       'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'MARA',  'name': 'Marathon Digital',     'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'RIOT',  'name': 'Riot Platforms',       'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'COIN',  'name': 'Coinbase',             'market': 'NASDAQ', 'sector': 'Financials'},
    {'ticker': 'CLSK',  'name': 'CleanSpark',           'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'HUT',   'name': 'Hut 8 Corp',           'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'BTBT',  'name': 'Bit Digital',          'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'CRCL',  'name': 'Circle Internet',      'market': 'NYSE',   'sector': 'Financials'},
    # BITM delisted
    {'ticker': 'CIFR',  'name': 'Cipher Mining',        'market': 'NASDAQ', 'sector': 'Technology'},
    # EV / Clean Energy
    {'ticker': 'RIVN',  'name': 'Rivian',               'market': 'NASDAQ', 'sector': 'Consumer Discretionary'},
    {'ticker': 'LCID',  'name': 'Lucid Group',          'market': 'NASDAQ', 'sector': 'Consumer Discretionary'},
    {'ticker': 'PLUG',  'name': 'Plug Power',           'market': 'NASDAQ', 'sector': 'Energy'},
    {'ticker': 'CHPT',  'name': 'ChargePoint',          'market': 'NYSE',   'sector': 'Industrials'},
    # Space / Defense
    {'ticker': 'RKLB',  'name': 'Rocket Lab',           'market': 'NASDAQ', 'sector': 'Industrials'},
    {'ticker': 'ASTS',  'name': 'AST SpaceMobile',      'market': 'NASDAQ', 'sector': 'Communication'},
    {'ticker': 'JOBY',  'name': 'Joby Aviation',        'market': 'NYSE',   'sector': 'Industrials'},
    {'ticker': 'ACHR',  'name': 'Archer Aviation',      'market': 'NYSE',   'sector': 'Industrials'},
    {'ticker': 'LUNR',  'name': 'Intuitive Machines',   'market': 'NASDAQ', 'sector': 'Industrials'},
    {'ticker': 'RDW',   'name': 'Redwire',              'market': 'NYSE',   'sector': 'Industrials'},
    # Biotech / Healthcare
    {'ticker': 'MRNA',  'name': 'Moderna',              'market': 'NASDAQ', 'sector': 'Health Care'},
    {'ticker': 'NVAX',  'name': 'Novavax',              'market': 'NASDAQ', 'sector': 'Health Care'},
    {'ticker': 'RXRX',  'name': 'Recursion Pharma',     'market': 'NASDAQ', 'sector': 'Health Care'},
    {'ticker': 'CRSP',  'name': 'CRISPR Therapeutics',  'market': 'NASDAQ', 'sector': 'Health Care'},
    {'ticker': 'BEAM',  'name': 'Beam Therapeutics',    'market': 'NASDAQ', 'sector': 'Health Care'},
    # Fintech / Payments
    {'ticker': 'AFRM',  'name': 'Affirm',               'market': 'NASDAQ', 'sector': 'Financials'},
    {'ticker': 'HOOD',  'name': 'Robinhood',             'market': 'NASDAQ', 'sector': 'Financials'},
    {'ticker': 'SQ',    'name': 'Block',                 'market': 'NYSE',   'sector': 'Financials'},
    {'ticker': 'SOFI',  'name': 'SoFi Technologies',    'market': 'NASDAQ', 'sector': 'Financials'},
    {'ticker': 'UPST',  'name': 'Upstart',              'market': 'NASDAQ', 'sector': 'Financials'},
    # Cloud / SaaS
    {'ticker': 'SNOW',  'name': 'Snowflake',            'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'DDOG',  'name': 'Datadog',              'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'NET',   'name': 'Cloudflare',           'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'CRWD',  'name': 'CrowdStrike',          'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'PANW',  'name': 'Palo Alto Networks',   'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'MDB',   'name': 'MongoDB',              'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'NOW',   'name': 'ServiceNow',           'market': 'NYSE',   'sector': 'Technology'},
    # Semiconductors
    {'ticker': 'AMD',   'name': 'AMD',                  'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'MU',    'name': 'Micron Technology',    'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'ON',    'name': 'ON Semiconductor',     'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'AMAT',  'name': 'Applied Materials',    'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'LRCX',  'name': 'Lam Research',         'market': 'NASDAQ', 'sector': 'Technology'},
    {'ticker': 'TSM',   'name': 'TSMC ADR',             'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'ASML',  'name': 'ASML',                 'market': 'NASDAQ', 'sector': 'Technology'},
    # Consumer / Tech
    {'ticker': 'SHOP',  'name': 'Shopify',              'market': 'NYSE',   'sector': 'Technology'},
    {'ticker': 'UBER',  'name': 'Uber',                 'market': 'NYSE',   'sector': 'Industrials'},
    {'ticker': 'ABNB',  'name': 'Airbnb',               'market': 'NASDAQ', 'sector': 'Consumer Discretionary'},
    # Meme / High-retail
    {'ticker': 'GME',   'name': 'GameStop',             'market': 'NYSE',   'sector': 'Consumer Discretionary'},
    # Commodities
    {'ticker': 'MP',    'name': 'MP Materials',         'market': 'NYSE',   'sector': 'Materials'},
    {'ticker': 'FCX',   'name': 'Freeport-McMoRan',     'market': 'NYSE',   'sector': 'Materials'},
    {'ticker': 'GOLD',  'name': 'Barrick Gold',         'market': 'NYSE',   'sector': 'Materials'},
    {'ticker': 'NEM',   'name': 'Newmont',              'market': 'NYSE',   'sector': 'Materials'},
]

# 테스트 유니버스 (각 시장 약 50종목)
KR_TEST = KR_FALLBACK
US_TEST = US_LARGE_CAP + [
    t for t in US_GROWTH_EXTENDED
    if t['ticker'] in {
        'PLTR', 'MSTR', 'MARA', 'RIOT', 'COIN', 'RIVN', 'RKLB', 'ASTS',
        'MRNA', 'AFRM', 'HOOD', 'SOFI', 'SNOW', 'DDOG', 'CRWD', 'SOUN',
        'AMD',  'MU',   'SMCI', 'SHOP', 'UBER', 'GME',  'NET',  'BBAI',
        'IREN', 'CLSK', 'HUT',  'JOBY', 'ACHR', 'IONQ', 'CRCL',
        'RGTI', 'QUBT', 'ARM',  'PANW', 'UPST',
    }
]


# ─── Market summary ───────────────────────────────────────────────────────────

def get_market_summary() -> dict:
    syms = {'kospi': '^KS11', 'kosdaq': '^KQ11', 'sp500': '^GSPC', 'nasdaq': '^IXIC'}
    result = {}
    for key, sym in syms.items():
        try:
            d = yf.download(sym, period='5d', progress=False, auto_adjust=True)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            if d is not None and len(d) >= 2:
                curr = float(d['Close'].iloc[-1])
                prev = float(d['Close'].iloc[-2])
                result[key] = {'index': round(curr, 2), 'change_pct': round((curr - prev) / prev * 100, 2)}
            else:
                result[key] = {'index': 0, 'change_pct': 0}
        except Exception:
            result[key] = {'index': 0, 'change_pct': 0}
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

MIN_SCORE = 40  # 최소 점수 기준

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test',    action='store_true', help='각 시장 ~50종목 빠른 테스트')
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
    for k, v in mkt.items():
        print(f"  {k.upper():8s}  {v['index']:>10,.2f}  ({v['change_pct']:+.2f}%)")

    results = {'kr': [], 'us': []}

    # ── 한국 ──────────────────────────────────────────────────────────────────
    if not args.us_only:
        print("\n🇰🇷  한국 종목 스캔...")
        print("  필터: 20일 평균 거래량 5만주 이상, 주가 1000원 이상")
        kr_list = KR_TEST if args.test else get_kr_universe()
        kr_cands, passed = [], 0
        for i, info in enumerate(kr_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(kr_list)}] {info['ticker']:<14} {info['name']:<14}")
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
            time.sleep(0.15)
        print(f"\n  통과: {passed}/{len(kr_list)}종목")
        # MIN_SCORE 이상인 종목만 포함, 미달시 있는 만큼 표시
        kr_filtered = [s for s in kr_cands if s['score'] >= MIN_SCORE]
        if len(kr_filtered) < 5:
            # 5개 미만이면 점수 하한 없이 상위 10개 표시
            kr_filtered = kr_cands
        kr_top = sorted(kr_filtered, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(kr_top):
            s['rank'] = i + 1
        results['kr'] = kr_top
        kr_summary = [f"{s['name']}({s['score']}점)" for s in kr_top]
        print(f"  KR TOP{len(kr_top)}: {kr_summary}")

    # ── 미국 ──────────────────────────────────────────────────────────────────
    if not args.kr_only:
        print("\n🇺🇸  미국 종목 스캔...")
        print("  필터: 20일 평균 거래량 10만주 이상, 주가 $1 이상")
        us_list = US_TEST if args.test else get_us_universe()
        us_cands, passed = [], 0
        for i, info in enumerate(us_list):
            sys.stdout.write(f"\r  [{i+1:3d}/{len(us_list)}] {info['ticker']:<8} {info['name']:<22}")
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
            time.sleep(0.15)
        print(f"\n  통과: {passed}/{len(us_list)}종목")
        us_filtered = [s for s in us_cands if s['score'] >= MIN_SCORE]
        if len(us_filtered) < 5:
            us_filtered = us_cands
        us_top = sorted(us_filtered, key=lambda x: x['score'], reverse=True)[:10]
        for i, s in enumerate(us_top):
            s['rank'] = i + 1
        results['us'] = us_top
        us_summary = [f"{s['ticker']}({s['score']}점)" for s in us_top]
        print(f"  US TOP{len(us_top)}: {us_summary}")

    # ── 저장 ──────────────────────────────────────────────────────────────────
    output = {
        'updated_at': now.isoformat(),
        'market_summary': mkt,
        'screening_results': results,
    }
    out_dir = Path(__file__).parent.parent / 'public' / 'data'
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in [out_dir / 'latest.json', out_dir / f'{now.strftime("%Y-%m-%d")}.json']:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=_default)
    print(f"\n✅ 저장: {out_dir}/latest.json")

    # 7일치만 보관
    for old in sorted(out_dir.glob('????-??-??.json'))[:-7]:
        old.unlink()

    print(f"🎉 완료!  KR {len(results['kr'])}개 + US {len(results['us'])}개\n")


if __name__ == '__main__':
    main()
