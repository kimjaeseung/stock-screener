"""
Pipeline entry point — fetches top NASDAQ stocks and writes docs/data.json.
Run: python scripts/run.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Allow imports from the same scripts/ directory
sys.path.insert(0, str(Path(__file__).parent))

from top100 import fetch_top100          # noqa: E402
from data_fetcher import fetch_all_sync  # noqa: E402
from screener import run_screener        # noqa: E402

OUT_FILE = Path(__file__).parent.parent.parent / "docs" / "data.json"


def get_spy_20d() -> float:
    """Fetch SPY 20-day return via yfinance."""
    try:
        import yfinance as yf
        df = yf.download("SPY", period="60d", interval="1d",
                         auto_adjust=True, progress=False)
        if df is not None and len(df) >= 21:
            if hasattr(df.columns, 'get_level_values'):
                df.columns = df.columns.get_level_values(0)
            closes = df["Close"].dropna()
            if len(closes) >= 21:
                return float((closes.iloc[-1] / closes.iloc[-21] - 1) * 100)
    except Exception as e:
        print(f"[SPY] failed: {e}")
    return 0.0


def main():
    print("[run] Fetching top 100 NASDAQ tickers...")
    tickers = fetch_top100()
    print(f"[run] Got {len(tickers)} tickers: {tickers[:10]}...")

    print("[run] Fetching OHLCV data...")
    data_map = fetch_all_sync(tickers, period="6mo", batch_size=20)
    ok = sum(1 for v in data_map.values() if v is not None)
    print(f"[run] Fetched {ok}/{len(tickers)} stocks successfully")

    spy_20d = get_spy_20d()
    print(f"[run] SPY 20d return: {spy_20d:.2f}%")

    top_stocks = run_screener(data_map, spy_20d=spy_20d, top_n=10)
    print(f"[run] Top {len(top_stocks)} stocks scored")
    for i, s in enumerate(top_stocks):
        print(f"  #{i+1} {s['ticker']}: {s['score']} pts — {s['signals'][:2]}")

    out = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "spy_20d": round(spy_20d, 2),
        "top100_count": ok,
        "stocks": top_stocks,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[run] Saved → {OUT_FILE}")


if __name__ == "__main__":
    main()
