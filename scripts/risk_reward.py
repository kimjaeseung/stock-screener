"""손익비 (Risk:Reward Ratio) 계산 모듈"""
import pandas as pd
import numpy as np
from indicators import calculate_fibonacci, find_swing_points


def calculate_risk_reward(df: pd.DataFrame) -> dict | None:
    """
    진입가, 손절가, 목표가, 손익비 계산
    손익비 2:1 미만이면 None 반환
    """
    if len(df) < 30:
        return None

    latest = df.iloc[-1]
    close = float(latest['Close'])

    # ATR 계산
    atr_col = [c for c in df.columns if c.startswith('ATR_')]
    atr = float(df[atr_col[0]].iloc[-1]) if atr_col else close * 0.02

    # MA60
    ma60_col = [c for c in df.columns if 'SMA_60' in c]
    ma60 = float(df[ma60_col[0]].iloc[-1]) if ma60_col else close * 0.95

    # 피보나치 및 스윙 포인트
    fib = calculate_fibonacci(df, 60)
    swing = find_swing_points(df, 10)

    # ── 손절가 계산 ──
    # max(스윙 저점, 현재가 - 2*ATR, MA60) 중 현재가와 가장 가까운 값
    stop_candidates = [
        swing['swing_low'],
        close - 2.0 * atr,
        ma60,
    ]
    # 현재가보다 낮은 후보만 필터
    valid_stops = [s for s in stop_candidates if s < close * 0.99]
    if not valid_stops:
        return None

    # 가장 현재가에 가까운 손절 (너무 작지 않게: 최소 1% 하락)
    stop_loss = max(valid_stops)
    if stop_loss >= close * 0.99:
        return None

    # ── 목표가 계산 ──
    # min(스윙 고점, 피보나치 확장 161.8%, 볼린저 상단) 중 현재가와 가장 가까운 값
    bb_upper_col = [c for c in df.columns if c.startswith('BBU_')]
    bb_upper = float(df[bb_upper_col[0]].iloc[-1]) if bb_upper_col else close * 1.05

    target_candidates = [
        swing['swing_high'],
        fib['fib_ext_1618'],
        bb_upper,
    ]
    # 현재가보다 높은 후보만 필터 (최소 2% 이상)
    valid_targets = [t for t in target_candidates if t > close * 1.02]
    if not valid_targets:
        return None

    take_profit = min(valid_targets)

    # ── 손익비 계산 ──
    risk = close - stop_loss
    reward = take_profit - close

    if risk <= 0:
        return None

    ratio = reward / risk

    if ratio < 2.0:
        return None

    return {
        'entry': round(close, 2),
        'stop_loss': round(stop_loss, 2),
        'take_profit': round(take_profit, 2),
        'risk': round(risk, 2),
        'reward': round(reward, 2),
        'ratio': round(ratio, 2),
        'risk_pct': round((stop_loss - close) / close * 100, 1),
        'reward_pct': round((take_profit - close) / close * 100, 1),
    }
