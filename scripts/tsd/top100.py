"""
Finviz NASDAQ Top 100 scraper — sorted by volume*price (dollar volume).
Caches result for 24 hours.
"""
import time
import json
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_FILE = Path(__file__).parent / "cache_top100.json"
CACHE_TTL = 86400  # 24 hours

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


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
    CACHE_FILE.write_text(json.dumps({"ts": time.time(), "tickers": tickers}))


def _parse_number(s: str) -> float:
    """Parse finviz number strings like '1.23B', '456M', '1,234'."""
    s = s.strip().replace(",", "")
    if not s or s == "-":
        return 0.0
    try:
        mult = 1.0
        if s.endswith("B"):
            mult = 1e9
            s = s[:-1]
        elif s.endswith("M"):
            mult = 1e6
            s = s[:-1]
        elif s.endswith("K"):
            mult = 1e3
            s = s[:-1]
        return float(s) * mult
    except ValueError:
        return 0.0


import re as _re

TICKER_RE = _re.compile(r'^[A-Z]{1,5}$')


def _is_valid_ticker(s: str) -> bool:
    return bool(TICKER_RE.match(s.strip()))


def fetch_top100() -> list[str]:
    """Return up to 100 NASDAQ tickers sorted by dollar volume."""
    cached = _load_cache()
    if cached:
        return cached

    tickers: list[dict] = []
    # Finviz screener: NASDAQ, price >$5, avg vol >500K, sorted by volume desc
    for offset in range(0, 500, 100):
        url = (
            "https://finviz.com/screener.ashx?v=111"
            "&f=exch_nasd,sh_price_o5,sh_avgvol_o500"
            f"&r={offset + 1}"
            "&o=-volume"
        )
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"[top100] fetch error at offset {offset}: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Primary method: find ticker links (class="screener-link-primary")
        ticker_links = soup.find_all("a", class_="screener-link-primary")
        found_in_page = []
        for a in ticker_links:
            t = a.get_text(strip=True)
            if _is_valid_ticker(t):
                found_in_page.append(t)

        if found_in_page:
            # Get prices and volumes from the same rows via td cells
            # Each row has: #, Ticker, Company, ..., Price, Change, Volume
            rows = soup.find_all("tr", class_=lambda c: c and "styled-row" in c)
            if not rows:
                # fallback: match ticker order to row index
                for t in found_in_page:
                    tickers.append({"ticker": t, "dollar_vol": 1.0})
            else:
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 10:
                        continue
                    t = cells[1].get_text(strip=True)
                    if not _is_valid_ticker(t):
                        continue
                    price = _parse_number(cells[8].get_text(strip=True))
                    vol = _parse_number(cells[9].get_text(strip=True))
                    if price > 0 and vol > 0:
                        tickers.append({"ticker": t, "dollar_vol": price * vol})
                    else:
                        tickers.append({"ticker": t, "dollar_vol": 1.0})

            if not tickers:
                # Links found but no structured rows — add with dummy dollar_vol
                for t in found_in_page:
                    tickers.append({"ticker": t, "dollar_vol": 1.0})
        else:
            print(f"[top100] no ticker links found at offset {offset}, stopping")
            break

        time.sleep(0.5)

    # Filter out any invalid tickers that slipped through
    tickers = [t for t in tickers if _is_valid_ticker(t["ticker"])]

    if not tickers:
        # Fallback: hardcoded liquid NASDAQ names
        fallback = [
            "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
            "AMD", "INTC", "QCOM", "MU", "NFLX", "ADBE", "CRM", "ORCL",
            "PYPL", "SHOP", "MRVL", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS",
            "PANW", "CRWD", "FTNT", "ZS", "OKTA", "DDOG", "SNOW", "PLTR",
            "COIN", "MSTR", "HOOD", "SOFI", "RBLX", "ABNB", "UBER", "LYFT",
            "SPOT", "DASH", "RIVN", "LCID", "NIO", "XPEV", "LI", "BIDU",
            "PDD", "JD", "BABA", "NTES", "TCOM", "TME", "BILI", "FUTU",
            "SOUN", "IONQ", "QBTS", "RGTI", "ARQT", "CRCL", "ACHR", "JOBY",
            "IREN", "CLSK", "HUT", "MARA", "RIOT", "CIFR", "BTBT", "WULF",
            "SMCI", "DELL", "HPE", "NTAP", "PSTG", "ESTC", "MDB", "GTLB",
            "TTD", "APPS", "PUBM", "MGNI", "IAS", "ZETA", "RAMP", "DV",
            "AEHR", "WOLF", "COHU", "ACLS", "FORM", "ONTO", "RTEX", "ICHR",
            "ENPH", "SEDG", "RUN", "SPWR", "FSLR", "ARRY", "BE", "PLUG",
        ]
        _save_cache(fallback)
        return fallback

    # Sort by dollar volume descending, take top 100
    tickers.sort(key=lambda x: x["dollar_vol"], reverse=True)
    result = [t["ticker"] for t in tickers[:100]]
    _save_cache(result)
    return result
