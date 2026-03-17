"""
Yahoo Finance data fetcher — uses yfinance library to handle auth/sessions.
"""
import time
import pandas as pd
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    raise ImportError("yfinance not installed: pip install yfinance")


def fetch_all_sync(
    tickers: list[str],
    period: str = "6mo",
    batch_size: int = 20,
    sleep: float = 0.5,
) -> dict[str, Optional[pd.DataFrame]]:
    """
    Download OHLCV data for all tickers using yfinance.
    Returns dict of ticker → DataFrame (or None on failure).
    """
    results: dict[str, Optional[pd.DataFrame]] = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_str = " ".join(batch)
        try:
            raw = yf.download(
                batch_str,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            print(f"[fetcher] batch {i//batch_size} download error: {e}")
            for t in batch:
                results[t] = None
            continue

        if raw is None or raw.empty:
            for t in batch:
                results[t] = None
            continue

        # Single ticker: columns are (Open, High, Low, Close, Volume)
        # Multi ticker: MultiIndex columns (Metric, Ticker)
        if len(batch) == 1:
            t = batch[0]
            df = raw.copy()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "Volume"])
            df = df[df["Volume"] > 0]
            results[t] = df if len(df) >= 20 else None
        else:
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).copy()
                        df = df.dropna(subset=["Close", "Volume"])
                        df = df[df["Volume"] > 0]
                        results[t] = df if len(df) >= 20 else None
                    except KeyError:
                        results[t] = None
            else:
                for t in batch:
                    results[t] = None

        ok = sum(1 for v in results.values() if v is not None)
        total = len(results)
        print(f"[fetcher] batch {i//batch_size + 1}/{(len(tickers)+batch_size-1)//batch_size} — {ok}/{total} ok")

        if i + batch_size < len(tickers):
            time.sleep(sleep)

    return results


async def fetch_batch(
    tickers: list[str],
    period: str = "6mo",
    batch_size: int = 20,
) -> dict[str, Optional[pd.DataFrame]]:
    """Async-compatible wrapper around fetch_all_sync."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: fetch_all_sync(tickers, period, batch_size)
    )
