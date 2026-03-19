"""
Pipeline entry point — writes public/data/latest.json (Vite SPA).

US 종목: docs/data.json (refresh_data.py · 6,000종목 정교 알고리즘) 변환
KR 종목: scripts/screener.py KR 스크리너 실행

우선순위:
  1. docs/data.json 존재 → US 데이터 변환 (정교한 알고리즘)
  2. 없으면 → 구 top-100 screener fallback
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))   # scripts/

ROOT          = Path(__file__).parent.parent.parent
DOCS_JSON     = ROOT / "docs" / "data.json"
KR_NAMES_JSON = ROOT / "docs" / "kr_names.json"
PUBLIC_DIR    = ROOT / "public" / "data"

# ── 신호 라벨 매핑 (refresh_data.py signals dict key → 한국어) ──────────────
SIGNAL_LABELS = {
    "golden_cross":     "골든크로스 (MA20>MA60)",
    "early_trend":      "조기 추세 전환 (MA5>MA20)",
    "ma_alignment":     "MA 완전 정렬 (5>20>60)",
    "macd_cross":       "MACD 골든크로스",
    "macd_turned":      "MACD 마이너스→플러스 전환",
    "volume_confirm":   "거래량 급증 (1.5x+)",
    "rsi_signal":       "RSI 모멘텀 존 (50-73)",
    "rsi_oversold":     "RSI 과매도 반등",
    "rsi_divergence":   "RSI 강세 다이버전스",
    "bollinger_break":  "볼린저 상단 돌파",
    "fib_support":      "피보나치 지지선",
    "stoch_signal":     "스토캐스틱 반등",
    "relative_strength": "SPY 대비 상대강도",
}


def _reels_to_spa_stock(s: dict, rank: int) -> dict:
    """docs/data.json 단일 종목 → SPA StockResult 포맷 변환."""
    det   = s.get("details", {})
    chart = s.get("chart", {})
    swing = s.get("swing", {})
    sigs  = s.get("signals", {})   # dict[str, bool]

    # 신호 → 문자열 리스트 (pre_gc_note 우선)
    signals_list: list[str] = []
    note = s.get("pre_gc_note", "")
    if note:
        signals_list.append(f"골든크로스 전조: {note}")
    for k, v in sigs.items():
        if v:
            signals_list.append(SIGNAL_LABELS.get(k, k))

    # 가격 히스토리 (30일)
    closes = chart.get("close", [])
    price_history_30d = [round(float(v), 2) for v in closes[-30:]] if closes else []

    # MA 값
    ma20_arr = chart.get("ma20", [])
    ma60_arr = chart.get("ma60", [])
    ma_20 = round(float(ma20_arr[-1]), 2) if ma20_arr else 0.0
    ma_60 = round(float(ma60_arr[-1]), 2) if ma60_arr else 0.0

    # 지표
    rsi      = det.get("rsi", 50)
    macd     = det.get("macd", 0)
    vol_r    = s.get("vol_ratio", 1.0)
    bb_pos   = det.get("bb_position", 0.5)
    pre_gc   = s.get("pre_gc_score", 0)
    ret_20d  = det.get("ret_20d", 0)

    # score_breakdown (SPA 카테고리로 매핑)
    score_breakdown = {
        "trend":        min(int(pre_gc), 20),
        "golden_cross": 12 if sigs.get("golden_cross") else (8 if sigs.get("early_trend") else 0),
        "momentum":     16 if ret_20d > 10 else (10 if ret_20d > 5 else 5),
        "volume":       13 if vol_r >= 2.0 else (8 if vol_r >= 1.5 else (4 if vol_r >= 1.0 else 0)),
        "support":      8 if sigs.get("fib_support") else 0,
        "bollinger":    5 if sigs.get("bollinger_break") else 0,
    }

    # 손익 정보
    entry     = swing.get("entry_low", s.get("price", 0))
    stop      = swing.get("stop_loss", 0)
    tp        = swing.get("target1", 0)
    risk      = round(entry - stop, 2) if stop else 0
    reward    = round(tp - entry, 2) if tp else 0
    rr_ratio  = swing.get("rr_ratio", 2.0)
    stop_pct  = swing.get("stop_pct", -5.0)
    tp_pct    = swing.get("target1_pct", 10.0)

    checklist = {
        "above_ma200":         True,
        "golden_cross_recent": bool(det.get("golden_cross") or det.get("recent_gc")),
        "volume_surge":        vol_r >= 2.0,
        "rsi_healthy":         30 <= rsi <= 70,
        "macd_bullish":        macd > 0,
        "trend_strong":        pre_gc >= 14,
        "rr_ratio_good":       rr_ratio >= 2.0,
    }

    return {
        "rank":    rank + 1,
        "ticker":  s["ticker"],
        "name":    s.get("name", s["ticker"]),
        "market":  "NASDAQ",
        "sector":  s.get("sector", "Unknown"),
        "price":   s.get("price", 0),
        "change_pct": s.get("change_pct", 0),
        "score":   s.get("score", 0),
        "score_breakdown": score_breakdown,
        "signals": signals_list,
        "technicals": {
            "rsi_14":       round(float(rsi), 1),
            "macd":         round(float(macd), 4),
            "macd_signal":  0.0,
            "adx":          None,   # refresh_data.py는 ADX 미계산 (SPA에서 null 처리)
            "volume_ratio": round(float(vol_r), 2),
            "bb_position":  round(float(bb_pos), 3),
        },
        "risk_reward": {
            "entry":       round(float(entry), 2),
            "stop_loss":   round(float(stop), 2),
            "take_profit": round(float(tp), 2),
            "risk":        risk,
            "reward":      reward,
            "ratio":       round(float(rr_ratio), 2),
            "risk_pct":    round(float(stop_pct), 1),
            "reward_pct":  round(float(tp_pct), 1),
        },
        "price_history_30d": price_history_30d,
        "ma_20": ma_20,
        "ma_60": ma_60,
        "checklist": checklist,
    }


def _load_us_from_docs() -> tuple[list[dict], str | None]:
    """
    docs/data.json (refresh_data.py 출력)을 읽어 SPA 포맷 US 종목 리스트 반환.
    파일이 없으면 ([], None) 반환.
    """
    if not DOCS_JSON.exists():
        return [], None

    with open(DOCS_JSON, encoding="utf-8") as f:
        docs = json.load(f)

    stocks = docs.get("stocks", [])
    updated_at = docs.get("updated_at", None)
    spa_stocks = [_reels_to_spa_stock(s, i) for i, s in enumerate(stocks[:10])]
    return spa_stocks, updated_at


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


# ── KR screener (scripts/screener.py) ──────────────────────────────────────

def _run_kr_screener(benchmark_20d: float) -> list[dict]:
    """한국 종목 스크리닝 (KR_TEST ~50 주요 종목 · GitHub Actions 20분 제한 고려)."""
    try:
        from screener import KR_TEST as kr_universe, analyze
        print(f"[run] KR 유니버스: {len(kr_universe)}종목 (주요 종목)")
        results = []
        for info in kr_universe:
            r = analyze(info, is_kr=True, min_avg_vol=50_000,
                        min_price=1_000, benchmark_20d=benchmark_20d)
            if r:
                results.append(r)
        results.sort(key=lambda x: x["score"], reverse=True)
        top10 = results[:10]
        for i, s in enumerate(top10):
            s["rank"] = i + 1
        top10_str = ", ".join(f"{s['name']}({s['score']}점)" for s in top10)
        print(f"[run] KR TOP10: {top10_str}")
        return top10
    except Exception as e:
        print(f"[run] KR 스크리너 실패: {e}")
        return []


# ── US fallback (구 top-100 screener) ──────────────────────────────────────

def _run_us_fallback(benchmark_20d: float) -> list[dict]:
    """docs/data.json 없을 때 기존 top-100 방식으로 US 스캔."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from top100 import fetch_top100
        from data_fetcher import fetch_all_sync
        from screener import run_screener, _LEVERAGED_NAME_PATTERNS
        import yfinance as yf

        print("[run] [fallback] Fetching top-100 NASDAQ tickers...")
        tickers = fetch_top100()
        print(f"[run] [fallback] Got {len(tickers)} tickers")

        print("[run] [fallback] Batch-downloading OHLCV...")
        data_map = fetch_all_sync(tickers, period="6mo", batch_size=50)
        ok = sum(1 for v in data_map.values() if v is not None)
        print(f"[run] [fallback] Fetched {ok}/{len(tickers)} ok")

        top_stocks = run_screener(data_map, spy_20d=benchmark_20d, top_n=10)
        for i, s in enumerate(top_stocks):
            s["rank"] = i + 1
        return top_stocks
    except Exception as e:
        print(f"[run] [fallback] US 스크리너 실패: {e}")
        return []


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    now_utc = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f" Signal Deck Pipeline  {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}\n")

    try:
        _run_pipeline(now_kst, now_utc)
    except Exception as e:
        print(f"\n[run] ❌ Pipeline error: {e}")
        import traceback; traceback.print_exc()
        raise


def _run_pipeline(now_kst, now_utc):
    # 1. 시장 지수
    market   = get_market_summary()
    spy_20d  = market["sp500"]["change_pct"]
    kospi_20d = market["kospi"]["change_pct"]

    # 2. US 종목 — docs/data.json 우선 (refresh_data.py 정교 알고리즘)
    print("\n[run] US 종목 로드 중...")
    us_stocks, docs_updated_at = _load_us_from_docs()
    if us_stocks:
        print(f"[run] ✅ docs/data.json 변환 완료 ({len(us_stocks)}종목) [갱신: {docs_updated_at}]")
        print(f"[run] US TOP3: {[(s['ticker'], s['score']) for s in us_stocks[:3]]}")
    else:
        print("[run] ⚠ docs/data.json 없음 → fallback 스크리너 실행")
        us_stocks = _run_us_fallback(spy_20d)

    # 3. KR 종목
    print("\n[run] KR 종목 스크리닝 중...")
    kr_stocks = _run_kr_screener(kospi_20d)

    # 4. latest.json 저장
    updated_at = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    spa_out = {
        "updated_at":     updated_at,
        "market_summary": market,
        "screening_results": {
            "kr": kr_stocks,
            "us": us_stocks,
        },
    }

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = PUBLIC_DIR / "latest.json"
    dated_path  = PUBLIC_DIR / f"{now_kst.strftime('%Y-%m-%d')}.json"

    latest_path.write_text(json.dumps(spa_out, ensure_ascii=False, indent=2))
    dated_path.write_text(json.dumps(spa_out, ensure_ascii=False, indent=2))
    print(f"\n[run] ✅ 저장 → {latest_path}")
    print(f"[run] ✅ 저장 → {dated_path}")

    # 아카이브 7일치만 유지
    for old in sorted(PUBLIC_DIR.glob("????-??-??.json"))[:-7]:
        old.unlink()

    print(f"\n🎉 완료!  KR {len(kr_stocks)}개 + US {len(us_stocks)}개")
    print(f"   SP500 20d: {spy_20d:+.2f}%  |  {updated_at}\n")


if __name__ == "__main__":
    main()
