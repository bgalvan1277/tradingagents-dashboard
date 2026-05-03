"""Intelligence data services: fetch and cache OSINT data from free APIs."""

import time
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache: { key: (data, expiry_timestamp) }
_cache: dict[str, tuple[list, float]] = {}
CACHE_TTL = 3600  # 1 hour


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


async def get_congress_trades(limit: int = 100) -> list[dict]:
    """Fetch recent Congressional stock trades from House & Senate Stock Watcher."""
    cached = _get_cached("congress_trades")
    if cached is not None:
        return cached[:limit]

    trades = []

    # House trades
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com"
                "/data/all_transactions.json"
            )
            if resp.status_code == 200:
                house_data = resp.json()
                for t in house_data:
                    trades.append({
                        "chamber": "House",
                        "name": t.get("representative", "Unknown"),
                        "ticker": t.get("ticker", "N/A"),
                        "type": t.get("type", ""),
                        "amount": t.get("amount", ""),
                        "date": t.get("transaction_date", ""),
                        "disclosure_date": t.get("disclosure_date", ""),
                        "district": t.get("district", ""),
                        "party": t.get("party", ""),
                        "description": t.get("asset_description", ""),
                    })
                logger.info("Fetched %d House trades", len(house_data))
    except Exception as e:
        logger.warning("Failed to fetch House trades: %s", e)

    # Senate trades
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com"
                "/aggregate/all_transactions.json"
            )
            if resp.status_code == 200:
                senate_data = resp.json()
                for t in senate_data:
                    trades.append({
                        "chamber": "Senate",
                        "name": t.get("senator", t.get("full_name", "Unknown")),
                        "ticker": t.get("ticker", "N/A"),
                        "type": t.get("type", t.get("transaction_type", "")),
                        "amount": t.get("amount", ""),
                        "date": t.get("transaction_date", ""),
                        "disclosure_date": t.get("disclosure_date", ""),
                        "district": "",
                        "party": t.get("party", ""),
                        "description": t.get("asset_description", ""),
                    })
                logger.info("Fetched %d Senate trades", len(senate_data))
    except Exception as e:
        logger.warning("Failed to fetch Senate trades: %s", e)

    # Sort by date descending
    trades.sort(key=lambda x: x.get("date", ""), reverse=True)

    _set_cached("congress_trades", trades)
    return trades[:limit]
