"""스크리닝 점수 산출 모듈 (100점 만점)"""
import pandas as pd
import numpy as np
from indicators import (
    get_volume_ratio, get_ma_slope, get_bb_position,
    get_bb_width_percentile, calculate_fibonacci, find_swing_points
)


def score_trend(df: pd.DataFrame, latest: pd.Series) -> tuple[int, list[str]]:
    """1. 추세 조건 (최대 25점)"""
    score = 0
    signals = []

    close = latest['Close']
    ma5_col = [c for c in df.columns if 'SMA_5' in c]
    ma20_col = [c for c in df.columns if 'SMA_20' in c]
    ma60_col = [c for c in df.columns if 'SMA_60' in c]
    ma120_col = [c for c in df.columns if 'SMA_120' in c]
    ma200_col = [c for c in df.columns if 'SMA_200' in c]
    adx_col = [c for c in df.columns if c.startswith('ADX_')]

    ma5 = latest.get(ma5_col[0]) if ma5_col else None
    ma20 = latest.get(ma20_col[0]) if ma20_col else None
    ma60 = latest.get(ma60_col[0]) if ma60_col else None
    ma120 = latest.get(ma120_col[0]) if ma120_col else None
    ma200 = latest.get(ma200_col[0]) if ma200_col else None
    adx = latest.get(adx_col[0]) if adx_col else None

    # 이평선 정배열
    if ma5 and ma20 and ma60 and ma120:
        if ma5 > ma20 > ma60 > ma120:
            score += 10
            signals.append('이평선 정배열 (5>20>60>120)')

    # 200일선 위
    if ma200 and close > ma200:
        score += 5
        signals.append(f'200일선 위 (MA200: {ma200:.0f})')

    # ADX > 25
    if adx and adx > 25:
        score += 5
        signals.append(f'ADX {adx:.1f} (강한 추세)')

    # 20일선 기울기 양수
    ma20_key = ma20_col[0] if ma20_col else None
    if ma20_key:
        slope = get_ma_slope(df, ma20_key, 5)
        if slope > 0.005:
            score += 5
            signals.append('20일선 상승 추세')

    return min(score, 25), signals


def score_golden_cross(df: pd.DataFrame) -> tuple[int, list[str]]:
    """2. 골든크로스 / 추세 전환 (최대 20점)"""
    score = 0
    signals = []

    ma5_col = [c for c in df.columns if 'SMA_5' in c]
    ma20_col = [c for c in df.columns if 'SMA_20' in c]
    ma60_col = [c for c in df.columns if 'SMA_60' in c]
    macd_col = [c for c in df.columns if c.startswith('MACD_') and not c.startswith('MACDh_') and not c.startswith('MACDs_')]
    macds_col = [c for c in df.columns if c.startswith('MACDs_')]

    earned = 0

    # 5일선 / 20일선 골든크로스 (최근 5일)
    if ma5_col and ma20_col:
        ma5 = df[ma5_col[0]].dropna()
        ma20 = df[ma20_col[0]].dropna()
        recent5 = min(5, len(ma5) - 1)
        for i in range(-recent5, 0):
            try:
                if ma5.iloc[i - 1] < ma20.iloc[i - 1] and ma5.iloc[i] >= ma20.iloc[i]:
                    earned = max(earned, 10)
                    signals.append('5일선 20일선 골든크로스')
                    break
            except IndexError:
                pass

    # 20일선 / 60일선 골든크로스 (최근 10일)
    if ma20_col and ma60_col:
        ma20 = df[ma20_col[0]].dropna()
        ma60 = df[ma60_col[0]].dropna()
        recent10 = min(10, len(ma20) - 1)
        for i in range(-recent10, 0):
            try:
                if ma20.iloc[i - 1] < ma60.iloc[i - 1] and ma20.iloc[i] >= ma60.iloc[i]:
                    earned = max(earned, 10)
                    signals.append('20일선 60일선 골든크로스')
                    break
            except IndexError:
                pass

    # MACD 골든크로스 (최근 3일)
    if macd_col and macds_col:
        macd = df[macd_col[0]].dropna()
        macds = df[macds_col[0]].dropna()
        recent3 = min(3, len(macd) - 1)
        for i in range(-recent3, 0):
            try:
                if macd.iloc[i - 1] < macds.iloc[i - 1] and macd.iloc[i] >= macds.iloc[i]:
                    earned = max(earned, 10)
                    signals.append('MACD 골든크로스')
                    break
            except IndexError:
                pass

    # MACD > Signal (현재 강세)
    if macd_col and macds_col:
        macd_val = df[macd_col[0]].iloc[-1]
        macds_val = df[macds_col[0]].iloc[-1]
        if macd_val > macds_val:
            earned = max(earned, 5)

    score = min(earned, 20)
    return score, signals


def score_momentum(df: pd.DataFrame, latest: pd.Series) -> tuple[int, list[str]]:
    """3. 모멘텀 & 오실레이터 (최대 20점)"""
    score = 0
    signals = []

    rsi_col = [c for c in df.columns if c.startswith('RSI_')]
    stochk_col = [c for c in df.columns if c.startswith('STOCHk_')]
    stochd_col = [c for c in df.columns if c.startswith('STOCHd_')]
    macdh_col = [c for c in df.columns if c.startswith('MACDh_')]

    rsi = latest.get(rsi_col[0]) if rsi_col else None
    stochk = latest.get(stochk_col[0]) if stochk_col else None
    stochd = latest.get(stochd_col[0]) if stochd_col else None

    # RSI 적정 구간
    if rsi:
        if 40 <= rsi <= 60:
            score += 5
            signals.append(f'RSI {rsi:.0f} (적정 구간)')
        elif rsi < 30:
            # 과매도에서 반등 체크
            rsi_series = df[rsi_col[0]].dropna()
            if len(rsi_series) >= 3:
                prev_rsi = rsi_series.iloc[-3:-1]
                if (prev_rsi < 30).any() and rsi > 30:
                    score += 10
                    signals.append(f'RSI {rsi:.0f} — 과매도 탈출 반등')

    # 스토캐스틱 상향 돌파
    if stochk and stochd and stochk_col and stochd_col:
        k_series = df[stochk_col[0]].dropna()
        d_series = df[stochd_col[0]].dropna()
        if len(k_series) >= 2 and len(d_series) >= 2:
            if k_series.iloc[-2] < d_series.iloc[-2] and k_series.iloc[-1] >= d_series.iloc[-1]:
                score += 5
                signals.append(f'스토캐스틱 %K({stochk:.0f}) %D 상향 돌파')

    # MACD 히스토그램 증가
    if macdh_col:
        macdh = df[macdh_col[0]].dropna()
        if len(macdh) >= 3:
            if macdh.iloc[-1] > macdh.iloc[-2] > macdh.iloc[-3]:
                score += 5
                signals.append('MACD 히스토그램 증가 추세')

    return min(score, 20), signals


def score_volume(df: pd.DataFrame) -> tuple[int, list[str]]:
    """4. 거래량 시그널 (최대 15점)"""
    score = 0
    signals = []

    vol_ratio = get_volume_ratio(df, 20)

    if vol_ratio >= 2.0:
        score += 10
        signals.append(f'거래량 20일 평균 대비 {vol_ratio:.1f}배 급증')
    elif vol_ratio >= 1.5:
        score += 5
        signals.append(f'거래량 {vol_ratio:.1f}배 증가')

    # 거래량 증가 + 주가 상승
    if len(df) >= 2:
        price_up = df['Close'].iloc[-1] > df['Close'].iloc[-2]
        vol_up = df['Volume'].iloc[-1] > df['Volume'].iloc[-2]
        if price_up and vol_up:
            score += 5
            signals.append('거래량 증가 + 주가 상승 (수급 일치)')

    return min(score, 15), signals


def score_support(df: pd.DataFrame, latest: pd.Series) -> tuple[int, list[str]]:
    """5. 지지/저항 & 피보나치 (최대 10점)"""
    score = 0
    signals = []

    close = latest['Close']
    fib = calculate_fibonacci(df, 60)

    # 피보나치 38.2%~61.8% 구간
    if fib['fib_382'] <= close <= fib['fib_618']:
        score += 5
        signals.append(f'피보나치 38.2%~61.8% 지지 구간')
    elif fib['fib_236'] <= close <= fib['fib_382']:
        score += 3

    # 볼린저 하단 반등
    bb_lower_col = [c for c in df.columns if c.startswith('BBL_')]
    bb_upper_col = [c for c in df.columns if c.startswith('BBU_')]
    if bb_lower_col and bb_upper_col:
        bb_lower = latest.get(bb_lower_col[0])
        bb_upper = latest.get(bb_upper_col[0])
        if bb_lower:
            # 최근 5일 내 하단 터치 후 반등
            recent = df.tail(5)
            touched_lower = (recent['Low'] <= bb_lower * 1.01).any()
            if touched_lower and close > bb_lower:
                score += 5
                signals.append('볼린저 하단 반등')

    # 이동평균선 지지
    ma20_col = [c for c in df.columns if 'SMA_20' in c]
    ma60_col = [c for c in df.columns if 'SMA_60' in c]
    if ma20_col:
        ma20 = latest.get(ma20_col[0])
        if ma20 and abs(close - ma20) / ma20 < 0.02:
            score = min(score + 5, 10)
            signals.append('20일선 지지 확인')
    if ma60_col and score < 10:
        ma60 = latest.get(ma60_col[0])
        if ma60 and abs(close - ma60) / ma60 < 0.02:
            score = min(score + 5, 10)
            signals.append('60일선 지지 확인')

    return min(score, 10), signals


def score_bollinger(df: pd.DataFrame) -> tuple[int, list[str]]:
    """6. 볼린저 밴드 스퀴즈 (최대 10점)"""
    score = 0
    signals = []

    bb_pct = get_bb_width_percentile(df, 120)

    if bb_pct <= 0.20:
        score += 5
        signals.append(f'볼린저 스퀴즈 (BB폭 하위 {bb_pct*100:.0f}%)')

    # 스퀴즈 후 상단 돌파
    bb_upper_col = [c for c in df.columns if c.startswith('BBU_')]
    if bb_upper_col and bb_pct <= 0.20:
        bb_upper = df[bb_upper_col[0]].iloc[-1]
        close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        prev_bb_upper = df[bb_upper_col[0]].iloc[-2]
        if close > bb_upper and prev_close <= prev_bb_upper:
            score += 5
            signals.append('스퀴즈 후 볼린저 상단 돌파')

    return min(score, 10), signals


def calculate_total_score(df: pd.DataFrame) -> dict:
    """전체 점수 계산 및 시그널 수집"""
    if len(df) < 60:
        return None

    latest = df.iloc[-1]

    s1, sig1 = score_trend(df, latest)
    s2, sig2 = score_golden_cross(df)
    s3, sig3 = score_momentum(df, latest)
    s4, sig4 = score_volume(df)
    s5, sig5 = score_support(df, latest)
    s6, sig6 = score_bollinger(df)

    total = s1 + s2 + s3 + s4 + s5 + s6

    all_signals = sig1 + sig2 + sig3 + sig4 + sig5 + sig6

    return {
        'total': total,
        'breakdown': {
            'trend': s1,
            'golden_cross': s2,
            'momentum': s3,
            'volume': s4,
            'support': s5,
            'bollinger': s6,
        },
        'signals': all_signals[:6],  # 상위 6개만
    }
