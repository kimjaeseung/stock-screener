"""기술적 분석 지표 계산 모듈"""
import pandas as pd
import pandas_ta as ta
import numpy as np


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """모든 기술적 지표를 계산하여 DataFrame에 추가"""
    if len(df) < 60:
        return df

    # 이동평균선 (SMA)
    for length in [5, 10, 20, 60, 120, 200]:
        df.ta.sma(length=length, append=True)

    # 지수이동평균 (EMA)
    for length in [12, 26, 50]:
        df.ta.ema(length=length, append=True)

    # RSI (14일)
    df.ta.rsi(length=14, append=True)

    # MACD
    df.ta.macd(fast=12, slow=26, signal=9, append=True)

    # 볼린저 밴드 (20일, 2σ)
    df.ta.bbands(length=20, std=2, append=True)

    # ATR (14일) — 손절 계산용
    df.ta.atr(length=14, append=True)

    # ADX (추세 강도)
    df.ta.adx(length=14, append=True)

    # 스토캐스틱
    df.ta.stoch(k=14, d=3, append=True)

    return df


def calculate_fibonacci(df: pd.DataFrame, lookback: int = 60) -> dict:
    """최근 고점/저점 기준 피보나치 되돌림 레벨 계산"""
    recent = df.tail(lookback)
    high = recent['High'].max()
    low = recent['Low'].min()
    diff = high - low

    return {
        'high': high,
        'low': low,
        'fib_236': high - diff * 0.236,
        'fib_382': high - diff * 0.382,
        'fib_500': high - diff * 0.500,
        'fib_618': high - diff * 0.618,
        'fib_ext_1618': high + diff * 0.618,
    }


def find_swing_points(df: pd.DataFrame, window: int = 10) -> dict:
    """최근 스윙 고점/저점 탐지"""
    prices = df['Close'].values
    highs = []
    lows = []

    for i in range(window, len(prices) - window):
        if prices[i] == max(prices[i - window:i + window + 1]):
            highs.append((i, prices[i]))
        if prices[i] == min(prices[i - window:i + window + 1]):
            lows.append((i, prices[i]))

    recent_high = highs[-1][1] if highs else df['High'].tail(30).max()
    recent_low = lows[-1][1] if lows else df['Low'].tail(30).min()

    return {'swing_high': recent_high, 'swing_low': recent_low}


def get_volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    """당일 거래량 / N일 평균 거래량"""
    if len(df) < period + 1:
        return 1.0
    avg_vol = df['Volume'].tail(period + 1).head(period).mean()
    current_vol = df['Volume'].iloc[-1]
    return current_vol / avg_vol if avg_vol > 0 else 1.0


def get_ma_slope(df: pd.DataFrame, ma_col: str, periods: int = 5) -> float:
    """이동평균선 기울기 (최근 N일 변화율)"""
    if ma_col not in df.columns or len(df) < periods + 1:
        return 0.0
    series = df[ma_col].dropna()
    if len(series) < periods:
        return 0.0
    slope = (series.iloc[-1] - series.iloc[-periods]) / series.iloc[-periods]
    return float(slope)


def get_bb_position(close: float, bb_upper: float, bb_lower: float) -> float:
    """볼린저 밴드 내 현재 위치 (0~1)"""
    band_width = bb_upper - bb_lower
    if band_width == 0:
        return 0.5
    return (close - bb_lower) / band_width


def get_bb_width_percentile(df: pd.DataFrame, lookback: int = 120) -> float:
    """BB 폭의 최근 N일 내 백분위 (낮을수록 스퀴즈)"""
    bb_upper_col = [c for c in df.columns if c.startswith('BBU_')]
    bb_lower_col = [c for c in df.columns if c.startswith('BBL_')]

    if not bb_upper_col or not bb_lower_col:
        return 0.5

    bb_width = df[bb_upper_col[0]] - df[bb_lower_col[0]]
    recent_width = bb_width.dropna().tail(lookback)

    if len(recent_width) < 10:
        return 0.5

    current = recent_width.iloc[-1]
    percentile = (recent_width < current).sum() / len(recent_width)
    return float(percentile)
