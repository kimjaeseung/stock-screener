"""
Pipeline entry point — fetches top NASDAQ stocks and writes:
  - docs/data.json          (docs/ static pages + reels)
  - public/data/latest.json (Vite SPA)
  - public/data/YYYY-MM-DD.json (daily archive)
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from top100 import fetch_top100          # noqa: E402
from data_fetcher import fetch_all_sync  # noqa: E402
from screener import run_screener        # noqa: E402

ROOT = Path(__file__).parent.parent.parent
DOCS_JSON   = ROOT / "docs" / "data.json"
PUBLIC_DIR  = ROOT / "public" / "data"


# ── Market index helpers ────────────────────────────────────────────────────

def _pct_20d(ticker: str) -> float:
    try:
        import yfinance as yf
        df = yf.download(ticker, period="60d", interval="1d",
                         auto_adjust=True, progress=False)
        if df is not None and len(df) >= 21:
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)
            closes = df["Close"].dropna()
            if len(closes) >= 21:
                return round(float((closes.iloc[-1] / closes.iloc[-21] - 1) * 100), 2)
    except Exception as e:
        print(f"  [{ticker}] failed: {e}")
    return 0.0


def _last_close(ticker: str) -> float:
    try:
        import yfinance as yf
        df = yf.download(ticker, period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if df is not None and len(df) >= 1:
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)
            return round(float(df["Close"].dropna().iloc[-1]), 2)
    except Exception:
        pass
    return 0.0


def get_market_summary() -> dict:
    """Fetch SPY/QQQ/KOSPI/KOSDAQ 20d returns and last close."""
    print("[run] Fetching market indices...")
    indices = {
        "sp500":  {"yf": "SPY",   "label": "S&P 500"},
        "nasdaq": {"yf": "QQQ",   "label": "NASDAQ"},
        "kospi":  {"yf": "^KS11", "label": "KOSPI"},
        "kosdaq": {"yf": "^KQ11", "label": "KOSDAQ"},
    }
    summary = {}
    for key, info in indices.items():
        pct = _pct_20d(info["yf"])
        idx = _last_close(info["yf"])
        summary[key] = {"index": idx, "change_pct": pct}
        print(f"  {key:8s}: {idx:>10,.2f}  ({pct:+.2f}%)")
    return summary


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    now_utc = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f" TopStockDaily Screener  {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}\n")

    # 1. Market indices
    market = get_market_summary()
    spy_20d = market["sp500"]["change_pct"]

    # 2. Top 100 NASDAQ tickers
    print("\n[run] Fetching top 100 NASDAQ tickers...")
    tickers = fetch_top100()
    print(f"[run] Got {len(tickers)} tickers: {tickers[:5]}...")

    # 3. Batch OHLCV download (fast: 2 API calls instead of 100)
    print("\n[run] Batch-downloading OHLCV data...")
    data_map = fetch_all_sync(tickers, period="6mo", batch_size=50)
    ok = sum(1 for v in data_map.values() if v is not None)
    print(f"[run] Fetched {ok}/{len(tickers)} stocks ok")

    # 4. Score & rank
    print("\n[run] Scoring stocks...")
    top_stocks = run_screener(data_map, spy_20d=spy_20d, top_n=10)
    print(f"[run] Top {len(top_stocks)} stocks:")
    for i, s in enumerate(top_stocks):
        print(f"  #{i+1:2d} {s['ticker']:<6} score={s['score']:3d}  {s.get('signals',[''])[:2]}")

    updated_at = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    # 5. Write docs/data.json  (read by docs/index.html and docs/reels/)
    docs_out = {
        "updated_at":   updated_at,
        "spy_20d":      round(spy_20d, 2),
        "top100_count": ok,
        "stocks":       top_stocks,
    }
    DOCS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DOCS_JSON.write_text(json.dumps(docs_out, ensure_ascii=False, indent=2))
    print(f"\n[run] Saved → {DOCS_JSON}")

    # 6. Write public/data/latest.json  (read by Vite SPA)
    #    Transform top_stocks into the screening_results format the SPA expects
    def to_spa_stock(s: dict) -> dict:
        det = s.get("details", {})
        chart = s.get("chart", {})
        return {
            "rank":   s.get("rank", 0),
            "ticker": s["ticker"],
            "name":   s.get("name", s["ticker"]),
            "market": "NASDAQ",
            "sector": s.get("sector", "Unknown"),
            "price":  s.get("price", 0),
            "score":  s["score"],
            "signals": s.get("signals", []),
            "rs_diff":  round(s.get("rs_diff", 0), 2),
            "rs_bonus": s.get("rs_bonus", 0),
            "vol_ratio": round(s.get("vol_ratio", 1.0), 2),
            "technicals": {
                "rsi_14":      round(det.get("rsi", 50), 1),
                "macd":        round(det.get("macd", 0), 4),
                "macd_signal": 0,
                "adx":         0,
                "volume_ratio": round(s.get("vol_ratio", 1.0), 2),
                "bb_position": round(det.get("bb_squeeze", 1.0), 3),
            },
            "score_breakdown": {
                "trend":       15 if det.get("golden_cross") else 0,
                "golden_cross": 15 if det.get("golden_cross") else 0,
                "momentum":    10 if (det.get("ret_5d", 0) or 0) > 3 else 0,
                "volume":      10 if s.get("vol_ratio", 1) >= 1.5 else 0,
                "support":     0,
                "bollinger":   10 if (det.get("bb_squeeze", 1) or 1) < 0.85 else 0,
            },
            "risk_reward": s.get("risk_reward", {"ratio": 2.0, "entry": s.get("price", 0)}),
            "details":    det,
            "chart":      chart,
            "swing":      s.get("swing"),
        }

    spa_out = {
        "updated_at":      updated_at,
        "market_summary":  market,
        "screening_results": {
            "kr": [],
            "us": [to_spa_stock(s) for s in top_stocks],
        },
    }

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = PUBLIC_DIR / "latest.json"
    dated_path  = PUBLIC_DIR / f"{now_kst.strftime('%Y-%m-%d')}.json"

    latest_path.write_text(json.dumps(spa_out, ensure_ascii=False, indent=2))
    dated_path.write_text(json.dumps(spa_out, ensure_ascii=False, indent=2))
    print(f"[run] Saved → {latest_path}")
    print(f"[run] Saved → {dated_path}")

    # Keep only last 7 daily archives
    for old in sorted(PUBLIC_DIR.glob("????-??-??.json"))[:-7]:
        old.unlink()

    print(f"\n✅ 완료 — US {len(top_stocks)}개 스탁 스크리닝")
    print(f"   SPY 20d: {spy_20d:+.2f}%  |  {updated_at}\n")


if __name__ == "__main__":
    main()
