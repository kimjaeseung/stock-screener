"""
Yahoo Finance data fetcher — uses yfinance Ticker API (more reliable than download()).
"""
import time
import pandas as pd
from typing import Optional
import yfinance as yf


def _fetch_one(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty or len(df) < 20:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df = df.dropna(subset=["Close", "Volume"])
        df = df[df["Volume"] > 0]
        return df if len(df) >= 20 else None
    except Exception as e:
        print(f"[fetcher] {ticker}: {e}")
        return None


def fetch_all_sync(
    tickers: list[str],
    period: str = "6mo",
    batch_size: int = 10,
    sleep: float = 1.0,
) -> dict[str, Optional[pd.DataFrame]]:
    results: dict[str, Optional[pd.DataFrame]] = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers):
        results[ticker] = _fetch_one(ticker, period)
        if (i + 1) % batch_size == 0:
            ok = sum(1 for v in results.values() if v is not None)
            print(f"[fetcher] {i+1}/{total} — {ok} ok")
            time.sleep(sleep)
    ok = sum(1 for v in results.values() if v is not None)
    print(f"[fetcher] done: {ok}/{total} ok")
    return results


async def fetch_batch(
    tickers: list[str],
    period: str = "6mo",
    batch_size: int = 10,
) -> dict[str, Optional[pd.DataFrame]]:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: fetch_all_sync(tickers, period, batch_size)
    )
