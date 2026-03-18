"""
Finviz NASDAQ Top 100 scraper — sorted by volume*price (dollar volume).
Caches result for 24 hours. Graceful fallback to hardcoded liquid stocks.
"""
import re as _re
import time
import json
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_FILE = Path(__file__).parent / "cache_top100.json"
CACHE_TTL  = 86400  # 24 hours

# Rotate User-Agent to reduce Finviz blocking
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

TICKER_RE = _re.compile(r"^[A-Z]{1,5}$")

# Hardcoded fallback — top NASDAQ by market cap / liquidity
FALLBACK = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
    "AMD",  "QCOM", "MU",   "NFLX", "ADBE", "CRM",   "ORCL", "INTC",
    "PYPL", "SHOP", "MRVL", "AMAT", "LRCX", "KLAC",  "SNPS", "CDNS",
    "PANW", "CRWD", "FTNT", "ZS",   "OKTA", "DDOG",  "SNOW", "PLTR",
    "COIN", "MSTR", "HOOD", "SOFI", "RBLX", "ABNB",  "UBER", "LYFT",
    "SPOT", "DASH", "RIVN", "LCID", "NIO",  "XPEV",  "LI",   "BIDU",
    "PDD",  "JD",   "BABA", "NTES", "TCOM", "SOUN",  "IONQ", "QBTS",
    "RGTI", "ACHR", "JOBY", "IREN", "CLSK", "HUT",   "MARA", "RIOT",
    "SMCI", "DELL", "HPE",  "NTAP", "PSTG", "ESTC",  "MDB",  "GTLB",
    "TTD",  "ZETA", "RAMP", "ENPH", "FSLR", "ARRY",  "BE",   "PLUG",
    "ARM",  "INTU", "AMGN", "ISRG", "VRTX", "REGN",  "BIIB", "IDXX",
    "MELI", "CTAS", "CPRT", "ROST", "ODFL", "PCAR",  "FAST", "VRSK",
]


def _load_cache() -> list[str] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data["ts"] < CACHE_TTL:
            return data["tickers"]
    except Exception:
        pass
    return None


def _save_cache(tickers: list[str]) -> None:
    try:
        CACHE_FILE.write_text(json.dumps({"ts": time.time(), "tickers": tickers}))
    except Exception:
        pass


def _parse_number(s: str) -> float:
    s = s.strip().replace(",", "").replace("%", "")
    if not s or s == "-":
        return 0.0
    try:
        mult = 1.0
        if s.endswith("B"):
            mult = 1e9; s = s[:-1]
        elif s.endswith("M"):
            mult = 1e6; s = s[:-1]
        elif s.endswith("K"):
            mult = 1e3; s = s[:-1]
        return float(s) * mult
    except ValueError:
        return 0.0


def _is_valid(t: str) -> bool:
    return bool(TICKER_RE.match(t.strip()))


def _extract_tickers_from_soup(soup: BeautifulSoup) -> list[dict]:
    """
    Try multiple CSS strategies to extract tickers + dollar volume from Finviz HTML.
    Returns list of {"ticker": str, "dollar_vol": float}.
    """
    results = []

    # Strategy 1: <a class="screener-link-primary"> with structured rows
    links = soup.find_all("a", class_="screener-link-primary")
    if not links:
        # Strategy 2: links with href containing 'quote.ashx?t='
        links = soup.find_all("a", href=lambda h: h and "quote.ashx?t=" in h)

    tickers_in_page = [a.get_text(strip=True) for a in links if _is_valid(a.get_text(strip=True))]

    if not tickers_in_page:
        return results

    # Try to find table rows with price/volume data
    # Finviz uses multiple class names over time; try each
    for row_class in ["styled-row", "screener-body-table-nw", None]:
        if row_class:
            rows = soup.find_all("tr", class_=lambda c: c and row_class in c)
        else:
            # Fallback: any <tr> containing a screener-link-primary
            rows = [a.find_parent("tr") for a in links if a.find_parent("tr")]
            rows = [r for r in rows if r is not None]

        if not rows:
            continue

        for row in rows:
            cells = row.find_all("td")
            # Try to find ticker cell (usually cols 1 or 2)
            ticker = None
            for ci in range(min(4, len(cells))):
                t = cells[ci].get_text(strip=True)
                if _is_valid(t):
                    ticker = t
                    break
            if not ticker:
                continue

            # Try to parse price and volume from available cells
            dollar_vol = 1.0
            for ci_price in range(len(cells) - 1):
                price_raw = cells[ci_price].get_text(strip=True)
                p = _parse_number(price_raw)
                if 1 < p < 50000:  # looks like a stock price
                    # Volume likely in next cell
                    for ci_vol in range(ci_price + 1, min(ci_price + 4, len(cells))):
                        vol_raw = cells[ci_vol].get_text(strip=True)
                        v = _parse_number(vol_raw)
                        if v > 10000:  # looks like volume
                            dollar_vol = p * v
                            break
                    break

            results.append({"ticker": ticker, "dollar_vol": dollar_vol})

        if results:
            break  # found rows with first strategy

    # If no rows found but we have ticker links, add with dummy dollar_vol
    if not results and tickers_in_page:
        for t in tickers_in_page:
            results.append({"ticker": t, "dollar_vol": 1.0})

    return results


def fetch_top100() -> list[str]:
    """Return up to 100 NASDAQ tickers sorted by dollar volume."""
    cached = _load_cache()
    if cached:
        print(f"[top100] using cache ({len(cached)} tickers)")
        return cached

    all_entries: list[dict] = []
    success = False

    for offset in range(0, 500, 100):
        url = (
            "https://finviz.com/screener.ashx?v=111"
            "&f=exch_nasd,sh_price_o5,sh_avgvol_o500"
            f"&r={offset + 1}"
            "&o=-volume"
        )
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            resp.raise_for_status()

            # Detect block / CAPTCHA
            if "captcha" in resp.text.lower() or "access denied" in resp.text.lower():
                print(f"[top100] blocked at offset {offset} — using fallback")
                break

            soup    = BeautifulSoup(resp.text, "lxml")
            entries = _extract_tickers_from_soup(soup)

            if not entries:
                print(f"[top100] no entries at offset {offset}, stopping")
                break

            all_entries.extend(entries)
            success = True
            print(f"[top100] offset={offset}: {len(entries)} tickers (total {len(all_entries)})")
            time.sleep(0.8)

        except Exception as e:
            print(f"[top100] error at offset {offset}: {e}")
            break

    if not all_entries:
        print("[top100] scraping failed — using hardcoded fallback")
        _save_cache(FALLBACK)
        return FALLBACK

    # Deduplicate (keep highest dollar_vol per ticker)
    seen: dict[str, float] = {}
    for entry in all_entries:
        t = entry["ticker"]
        dv = entry["dollar_vol"]
        if t not in seen or dv > seen[t]:
            seen[t] = dv

    sorted_tickers = sorted(seen, key=lambda t: seen[t], reverse=True)
    result = sorted_tickers[:100]

    # If we got fewer than 20 real tickers, supplement with fallback
    if len(result) < 20:
        existing = set(result)
        for t in FALLBACK:
            if t not in existing:
                result.append(t)
            if len(result) >= 100:
                break

    print(f"[top100] final: {len(result)} tickers, top5={result[:5]}")
    _save_cache(result)
    return result
