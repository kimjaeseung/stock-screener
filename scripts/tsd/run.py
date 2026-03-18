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
KR_NAMES_JSON = ROOT / "docs" / "kr_names.json"
PUBLIC_DIR  = ROOT / "public" / "data"


def check_kr_names(tickers: list[str]) -> None:
    """top-2 티커가 kr_names.json 에 없으면 경고 출력."""
    if not KR_NAMES_JSON.exists():
        print(f"⚠ kr_names.json 없음 — {KR_NAMES_JSON}")
        return
    with open(KR_NAMES_JSON, encoding="utf-8") as f:
        kr = json.load(f)
    for t in tickers:
        if t not in kr:
            print(f"⚠ 한국어명 없음: {t} — kr_names.json 에 추가 필요")


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

def _enrich_stock_info(stocks: list[dict]) -> None:
    """
    Fetch name and sector from yfinance for top-2 stocks (lightweight fast_info).
    Modifies stocks in-place. Fails silently.
    """
    import yfinance as yf
    for s in stocks[:2]:
        ticker = s.get("ticker", "")
        if not ticker:
            continue
        try:
            info = yf.Ticker(ticker).info
            s["name"]   = info.get("shortName") or info.get("longName") or ticker
            s["sector"] = info.get("sector") or info.get("industryDisp") or "NASDAQ"
        except Exception:
            s.setdefault("name",   ticker)
            s.setdefault("sector", "NASDAQ")


def main():
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    now_utc = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f" TopStockDaily Screener  {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}\n")

    try:
        _run_pipeline(now_kst, now_utc)
    except Exception as e:
        print(f"\n[run] ❌ Pipeline error: {e}")
        import traceback; traceback.print_exc()
        # If previous output exists, keep it — do not overwrite with empty
        if DOCS_JSON.exists():
            print("[run] Keeping previous docs/data.json (no overwrite on failure)")
        raise  # Re-raise so GitHub Actions marks the step as failed (visible in logs)


def _run_pipeline(now_kst, now_utc):
    # 1. Market indices
    market  = get_market_summary()
    spy_20d = market["sp500"]["change_pct"]

    # 2. Top 100 NASDAQ tickers
    print("\n[run] Fetching top 100 NASDAQ tickers...")
    tickers = fetch_top100()
    print(f"[run] Got {len(tickers)} tickers: {tickers[:5]}...")

    if len(tickers) < 10:
        raise RuntimeError(f"Too few tickers: {len(tickers)}")

    # 3. Batch OHLCV download
    print("\n[run] Batch-downloading OHLCV data...")
    data_map = fetch_all_sync(tickers, period="6mo", batch_size=50)
    ok = sum(1 for v in data_map.values() if v is not None)
    print(f"[run] Fetched {ok}/{len(tickers)} stocks ok")

    if ok < 5:
        raise RuntimeError(f"Too few stocks fetched: {ok}")

    # 4. Score & rank
    print("\n[run] Scoring stocks...")
    top_stocks = run_screener(data_map, spy_20d=spy_20d, top_n=10)
    print(f"[run] Top {len(top_stocks)} stocks scored")

    if len(top_stocks) < 2:
        raise RuntimeError(f"Too few stocks scored: {len(top_stocks)}")

    # 4b. Enrich top-2 with name/sector from yfinance
    print("[run] Enriching top-2 with name/sector...")
    _enrich_stock_info(top_stocks)

    # 4c. kr_names.json 검증 (top-2)
    top2_tickers = [s["ticker"] for s in top_stocks[:2]]
    check_kr_names(top2_tickers)

    updated_at = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    # 5. Write docs/data.json  (read by docs/reels/)
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
    def to_spa_stock(s: dict) -> dict:
        det  = s.get("details", {})
        sigs = s.get("signals", {})
        return {
            "rank":    s.get("rank", 0),
            "ticker":  s["ticker"],
            "name":    s.get("name", s["ticker"]),
            "market":  "NASDAQ",
            "sector":  s.get("sector", "NASDAQ"),
            "price":   s.get("price", 0),
            "score":   s["score"],
            "signals": sigs,   # dict[str, bool]
            "rs_diff":   round(s.get("rs_diff", 0), 2),
            "rs_bonus":  s.get("rs_bonus", 0),
            "vol_ratio": round(s.get("vol_ratio", 1.0), 2),
            "atr":       s.get("atr", 0),
            "technicals": {
                "rsi_14":       round(det.get("rsi", 50), 1),
                "macd":         round(det.get("macd", 0), 4),
                "macd_crossed": det.get("macd_cross_recent", False),
                "golden_cross": det.get("golden_cross", False),
                "recent_gc":    det.get("recent_gc", False),
                "ma_aligned":   sigs.get("ma_alignment", False),
                "fib_support":  sigs.get("fib_support", False),
                "volume_ratio": round(s.get("vol_ratio", 1.0), 2),
                "bb_position":  round(det.get("bb_position", 0.5), 3),
                "stoch_k":      round(det.get("stoch_k", 50), 1),
                "dist_52w":     round(det.get("dist_52w", 0.2), 4),
                "ret_5d":       round(det.get("ret_5d", 0), 2),
                "ret_20d":      round(det.get("ret_20d", 0), 2),
            },
            "score_breakdown": {
                "golden_cross": 12 + (5 if det.get("recent_gc") else 0) if det.get("golden_cross") else 0,
                "volume":       10 if det.get("max_vol_5d", 0) >= 2.5 else (8 if det.get("vol_ratio", 0) >= 2.0 else 6 if det.get("vol_ratio", 0) >= 1.5 else 0),
                "rsi":          10 if 57 <= det.get("rsi", 0) <= 70 else 6,
                "macd":         10 if det.get("macd_cross_recent") else (8 if det.get("macd", 0) > 0 else 0),
                "ma_alignment": 8 if sigs.get("ma_alignment") else 0,
                "fib_support":  7 if sigs.get("fib_support") else 0,
                "rs_bonus":     s.get("rs_bonus", 0),
            },
            "risk_reward": {
                "ratio": s.get("swing", {}).get("rr_ratio", 2.0),
                "entry": s.get("price", 0),
            },
            "details":  det,
            "chart":    s.get("chart", {}),
            "swing":    s.get("swing"),
        }

    spa_out = {
        "updated_at":     updated_at,
        "market_summary": market,
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
    print(f"   SPY 20d: {spy_20d:+.2f}%  |  {updated_at}")
    print(f"   Top-2: {[s['ticker'] for s in top_stocks[:2]]}\n")


if __name__ == "__main__":
    main()
