"""
Yahoo Finance data fetcher — batch download via yf.download() for speed.
Downloads all tickers in parallel (one API call per batch), not one-by-one.
"""
import time
import pandas as pd
from typing import Optional
import yfinance as yf


def _extract_from_batch(raw: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """Extract a single ticker DataFrame from a multi-ticker batch download.

    yfinance MultiIndex column layout varies by version and group_by setting:
      group_by='ticker' → (ticker, field)  ← level 0 = ticker
      group_by='column' → (field, ticker)  ← level 1 = ticker
    We auto-detect which level holds ticker names.
    """
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            l0_vals = raw.columns.get_level_values(0).unique().tolist()
            l1_vals = raw.columns.get_level_values(1).unique().tolist()
            if ticker in l0_vals:
                df = raw.xs(ticker, axis=1, level=0)
            elif ticker in l1_vals:
                df = raw.xs(ticker, axis=1, level=1)
            else:
                # Ticker not found in either level — single-ticker download returns flat df
                df = raw.copy()
        else:
            df = raw.copy()

        needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        if len(needed) < 5:
            return None
        df = df[needed].copy().dropna(subset=["Close", "Volume"])
        df = df[df["Volume"] > 0]
        return df if len(df) >= 20 else None
    except Exception:
        return None


def _fetch_one(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Individual fallback fetch via Ticker.history()."""
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
    batch_size: int = 50,      # 50 tickers per API call — ~2 calls for top-100
    sleep: float = 0.5,        # short sleep between batches
) -> dict[str, Optional[pd.DataFrame]]:
    """
    Batch-download OHLCV for all tickers using yf.download().
    Auto-detects MultiIndex level so extraction never silently fails.
    Falls back to individual fetch if batch fails.
    """
    results: dict[str, Optional[pd.DataFrame]] = {}
    total = len(tickers)

    for start in range(0, total, batch_size):
        batch = tickers[start:start + batch_size]
        batch_num = start // batch_size + 1
        total_batches = (total - 1) // batch_size + 1
        print(f"[fetcher] batch {batch_num}/{total_batches}: {len(batch)} tickers...", end=" ", flush=True)

        batch_ok = False
        try:
            raw = yf.download(
                batch,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )

            if raw is None or raw.empty:
                raise ValueError("empty result")

            # Single-ticker download returns flat DataFrame
            if len(batch) == 1:
                results[batch[0]] = _extract_from_batch(raw, batch[0])
            else:
                for ticker in batch:
                    results[ticker] = _extract_from_batch(raw, ticker)

            batch_ok = True

        except Exception as e:
            print(f"\n[fetcher] batch error ({e}) — falling back to individual fetch")

        if not batch_ok:
            for ticker in batch:
                results[ticker] = _fetch_one(ticker, period)

        # Verify extraction quality; re-fetch failures individually
        if batch_ok and len(batch) > 1:
            failed = [t for t in batch if results.get(t) is None]
            if failed:
                print(f"\n[fetcher] re-fetching {len(failed)} failed tickers individually...")
                for ticker in failed:
                    results[ticker] = _fetch_one(ticker, period)

        ok = sum(1 for t in batch if results.get(t) is not None)
        print(f"{ok}/{len(batch)} ok")

        if start + batch_size < total:
            time.sleep(sleep)

    total_ok = sum(1 for v in results.values() if v is not None)
    print(f"[fetcher] done: {total_ok}/{total} ok")
    return results
