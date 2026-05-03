"""Intelligence data services: fetch and cache OSINT data from free APIs."""

import time
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache: { key: (data, expiry_timestamp) }
_cache: dict[str, tuple[list, float]] = {}
CACHE_TTL = 1800  # 30 minutes


def _get_cached(key: str) -> Optional[list]:
    """Return cached data if fresh, else None."""
    if key in _cache:
        data, expiry = _cache[key]
        if time.time() < expiry:
            return data
    return None


def _set_cached(key: str, data: list):
    """Store data in cache."""
    _cache[key] = (data, time.time() + CACHE_TTL)


SEC_HEADERS = {"User-Agent": "TradingAgents Dashboard support@tradingagents.website"}


async def get_insider_trades(limit: int = 100) -> list[dict]:
    """Fetch recent SEC Form 4 insider trades from EDGAR full-text search."""
    cached = _get_cached("insider_trades")
    if cached is not None:
        return cached[:limit]

    trades = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Fetch recent Form 4 filings from EDGAR
            resp = await client.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": "", "forms": "4", "dateRange": "custom", "startdt": "2026-04-01"},
                headers=SEC_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for h in hits:
                    src = h.get("_source", {})
                    names = src.get("display_names", [])
                    # First name is the insider, second is the company
                    insider_name = names[0].split("(CIK")[0].strip() if len(names) > 0 else "Unknown"
                    company_name = names[1].split("(CIK")[0].strip() if len(names) > 1 else "Unknown"
                    # Clean up names (remove trailing periods, extra spaces)
                    insider_name = " ".join(w.capitalize() for w in insider_name.lower().split())
                    company_name = company_name.replace("/DE/", "").replace("/", "").strip()

                    trades.append({
                        "date": src.get("file_date", ""),
                        "insider": insider_name,
                        "company": company_name,
                        "form": "Form 4",
                        "filing_id": src.get("adsh", ""),
                    })
                logger.info("Fetched %d Form 4 filings from SEC EDGAR", len(trades))
    except Exception as e:
        logger.warning("Failed to fetch SEC EDGAR data: %s", e)

    _set_cached("insider_trades", trades)
    return trades[:limit]


async def get_sec_filings(form_type: str = "8-K", limit: int = 50) -> list[dict]:
    """Fetch recent SEC filings of a given type from EDGAR."""
    cache_key = f"sec_{form_type}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached[:limit]

    filings = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": "", "forms": form_type, "dateRange": "custom", "startdt": "2026-04-01"},
                headers=SEC_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for h in hits:
                    src = h.get("_source", {})
                    names = src.get("display_names", [])
                    company = names[0].split("(CIK")[0].strip() if names else "Unknown"

                    filings.append({
                        "date": src.get("file_date", ""),
                        "company": company,
                        "form": form_type,
                        "description": src.get("file_description", ""),
                        "filing_id": src.get("adsh", ""),
                        "items": src.get("items", ""),
                    })
                logger.info("Fetched %d %s filings from SEC EDGAR", len(filings), form_type)
    except Exception as e:
        logger.warning("Failed to fetch SEC %s data: %s", form_type, e)

    _set_cached(cache_key, filings)
    return filings[:limit]
