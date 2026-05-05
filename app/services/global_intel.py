"""Global Intelligence service: macro news feeds, sentiment, and geopolitical signals.

Fetches and caches data from:
- RSS feeds: Reuters, CNBC, MarketWatch, Bloomberg, WSJ, Yahoo Finance
- FRED: Key economic indicators (reuses Col. Wolfe's pattern)
- yfinance: VIX, market breadth, Fear & Greed proxy
- GDELT: Geopolitical event pulse
"""

import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

# ── In-memory cache ────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 900  # 15 minutes for news feeds
_FRED_TTL = 3600  # 1 hour for economic data
_VIX_TTL = 300    # 5 minutes for VIX


def _get_cached(key: str) -> Optional[object]:
    """Return cached value if still fresh, else None."""
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < (_FRED_TTL if "fred" in key else _VIX_TTL if "vix" in key else _CACHE_TTL):
            return val
    return None


def _set_cached(key: str, val: object):
    _cache[key] = (time.time(), val)


# ── RSS FEED SOURCES ───────────────────────────────────────────────────────────

RSS_FEEDS = {
    "markets": [
        {"name": "Google Finance", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en", "icon": "google"},
        {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "icon": "cnbc"},
        {"name": "MarketWatch Top", "url": "https://feeds.marketwatch.com/marketwatch/topstories", "icon": "mw"},
        {"name": "Investing.com", "url": "https://www.investing.com/rss/news.rss", "icon": "inv"},
    ],
    "macro": [
        {"name": "Google Economy", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en", "icon": "google"},
        {"name": "CNBC Economy", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "icon": "cnbc"},
        {"name": "MarketWatch Economy", "url": "https://feeds.marketwatch.com/marketwatch/marketpulse", "icon": "mw"},
    ],
    "geopolitics": [
        {"name": "Google World", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en", "icon": "google"},
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "icon": "bbc"},
        {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "icon": "alj"},
    ],
    "tech": [
        {"name": "Google Tech", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB/sections/CAQiS0NCQVNNZ29JTDIwdk1EZGpNWFlTQW1WdUdnSlZVeUlPQ0FRYUNnb0lMMjB2TURKdGN6QXFEUW9MRWdsTmIySnBiR1VnUVhCd0tBQSouCAAqKAgAKiQICiIgQ0JBU0Vnb0lMMjB2TURkak1YWVNBbVZ1R2dKVlV5Z0FQAVAB?hl=en-US&gl=US&ceid=US:en", "icon": "google"},
        {"name": "CNBC Tech", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "icon": "cnbc"},
    ],
}


async def _parse_rss_feed(client: httpx.AsyncClient, feed: dict) -> list[dict]:
    """Parse a single RSS feed and return structured items."""
    items = []
    try:
        resp = await client.get(
            feed["url"],
            headers={"User-Agent": "Mozilla/5.0 (compatible; TradingAgents/1.0)"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("RSS feed %s returned %d", feed["name"], resp.status_code)
            return items

        root = ElementTree.fromstring(resp.text)
        # Handle both RSS 2.0 and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}

        for item in root.findall(".//item")[:8]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            # Clean description (strip HTML tags)
            if desc:
                import re
                desc = re.sub(r"<[^>]+>", "", desc).strip()
                if len(desc) > 200:
                    desc = desc[:197] + "..."

            # Parse pub date
            parsed_time = None
            if pub_date:
                for fmt in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S GMT",
                    "%Y-%m-%dT%H:%M:%S%z",
                ]:
                    try:
                        parsed_time = datetime.strptime(pub_date, fmt)
                        break
                    except ValueError:
                        continue

            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc or "",
                    "source": feed["name"],
                    "icon": feed["icon"],
                    "pub_date": pub_date,
                    "timestamp": parsed_time,
                })
    except Exception as e:
        logger.warning("Failed to parse RSS feed %s: %s", feed["name"], e)
    return items


async def fetch_news_feeds(category: str = "all") -> dict[str, list[dict]]:
    """Fetch all RSS feeds, grouped by category. Returns cached data if fresh."""
    cache_key = f"news_feeds_{category}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    results = {}
    categories = RSS_FEEDS if category == "all" else {category: RSS_FEEDS.get(category, [])}

    async with httpx.AsyncClient(timeout=15) as client:
        for cat_name, feeds in categories.items():
            tasks = [_parse_rss_feed(client, feed) for feed in feeds]
            feed_results = await asyncio.gather(*tasks, return_exceptions=True)

            all_items = []
            for result in feed_results:
                if isinstance(result, list):
                    all_items.extend(result)

            # Sort by timestamp (newest first), then deduplicate by title
            all_items.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
            seen_titles = set()
            deduped = []
            for item in all_items:
                title_key = item["title"].lower()[:60]
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    deduped.append(item)
            results[cat_name] = deduped[:20]

    _set_cached(cache_key, results)
    return results


# ── MARKET SENTIMENT (VIX + indices) ──────────────────────────────────────────

def _fetch_market_sentiment_sync() -> dict:
    """Fetch VIX, major indices, and compute a fear/greed proxy. Runs sync (yfinance)."""
    data = {
        "vix": None, "vix_change": None, "vix_signal": "N/A",
        "sp500": None, "sp500_change": None,
        "nasdaq": None, "nasdaq_change": None,
        "dow": None, "dow_change": None,
        "dxy": None, "dxy_change": None,
        "gold": None, "gold_change": None,
        "oil": None, "oil_change": None,
        "btc": None, "btc_change": None,
        "fear_greed_score": None, "fear_greed_label": "N/A",
    }
    try:
        import yfinance as yf

        tickers_map = {
            "^VIX": "vix", "^GSPC": "sp500", "^IXIC": "nasdaq", "^DJI": "dow",
            "DX-Y.NYB": "dxy", "GC=F": "gold", "CL=F": "oil", "BTC-USD": "btc",
        }

        fetched = yf.download(
            list(tickers_map.keys()),
            period="5d",
            progress=False,
            threads=True,
        )

        if fetched is not None and not fetched.empty:
            for yf_symbol, key in tickers_map.items():
                try:
                    # yfinance multi-ticker returns MultiIndex columns
                    close_col = ("Close", yf_symbol) if isinstance(fetched.columns, type(fetched.columns)) else "Close"
                    if isinstance(fetched.columns, type(fetched.columns)) and ("Close", yf_symbol) in fetched.columns:
                        closes = fetched[("Close", yf_symbol)].dropna()
                    else:
                        continue
                    if len(closes) >= 2:
                        current = float(closes.iloc[-1])
                        prev = float(closes.iloc[-2])
                        change = ((current - prev) / prev) * 100
                        data[key] = round(current, 2)
                        data[f"{key}_change"] = round(change, 2)
                except Exception:
                    continue

        # VIX-based fear/greed signal
        vix_val = data.get("vix")
        if vix_val:
            if vix_val > 30:
                data["vix_signal"] = "EXTREME FEAR"
                data["fear_greed_score"] = max(0, 50 - (vix_val - 20) * 2.5)
            elif vix_val > 20:
                data["vix_signal"] = "FEAR"
                data["fear_greed_score"] = max(15, 50 - (vix_val - 20) * 2)
            elif vix_val > 15:
                data["vix_signal"] = "NEUTRAL"
                data["fear_greed_score"] = 50
            elif vix_val > 12:
                data["vix_signal"] = "GREED"
                data["fear_greed_score"] = 65 + (15 - vix_val) * 3
            else:
                data["vix_signal"] = "EXTREME GREED"
                data["fear_greed_score"] = min(95, 80 + (12 - vix_val) * 5)

            data["fear_greed_score"] = round(data["fear_greed_score"])
            if data["fear_greed_score"] >= 75:
                data["fear_greed_label"] = "Extreme Greed"
            elif data["fear_greed_score"] >= 55:
                data["fear_greed_label"] = "Greed"
            elif data["fear_greed_score"] >= 45:
                data["fear_greed_label"] = "Neutral"
            elif data["fear_greed_score"] >= 25:
                data["fear_greed_label"] = "Fear"
            else:
                data["fear_greed_label"] = "Extreme Fear"

    except Exception as e:
        logger.warning("Market sentiment fetch failed: %s", e)
    return data


async def fetch_market_sentiment() -> dict:
    """Async wrapper for market sentiment. Returns cached data if fresh."""
    cache_key = "vix_sentiment"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _fetch_market_sentiment_sync)
    _set_cached(cache_key, data)
    return data


# ── FRED ECONOMIC SNAPSHOT ────────────────────────────────────────────────────

async def fetch_fred_snapshot() -> dict:
    """Fetch key FRED indicators for the macro dashboard."""
    cache_key = "fred_snapshot"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    indicators = {}
    series_map = {
        "Fed Funds Rate": "FEDFUNDS",
        "Unemployment": "UNRATE",
        "CPI (YoY)": "CPIAUCSL",
        "10Y Treasury": "DGS10",
        "2Y Treasury": "DGS2",
    }

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            for label, series_id in series_map.items():
                try:
                    resp = await client.get(
                        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                        headers={"User-Agent": "TradingAgents/1.0"},
                    )
                    if resp.status_code == 200:
                        lines = resp.text.strip().split("\n")
                        if len(lines) > 1:
                            parts = lines[-1].split(",")
                            if len(parts) >= 2 and parts[1].strip() not in (".", ""):
                                indicators[label] = {
                                    "value": parts[1].strip(),
                                    "date": parts[0].strip(),
                                }
                except Exception:
                    pass
    except Exception as e:
        logger.warning("FRED snapshot failed: %s", e)

    # Yield curve spread
    if "10Y Treasury" in indicators and "2Y Treasury" in indicators:
        try:
            spread = float(indicators["10Y Treasury"]["value"]) - float(indicators["2Y Treasury"]["value"])
            indicators["Yield Spread (10Y-2Y)"] = {
                "value": f"{spread:.2f}",
                "date": indicators["10Y Treasury"]["date"],
                "signal": "INVERTED" if spread < 0 else "NORMAL",
            }
        except (ValueError, KeyError):
            pass

    _set_cached(cache_key, indicators)
    return indicators


# ── GDELT GEOPOLITICAL PULSE ──────────────────────────────────────────────────

async def fetch_gdelt_events(limit: int = 15) -> list[dict]:
    """Fetch recent high-impact geopolitical events from GDELT."""
    cache_key = "gdelt_events"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    events = []
    try:
        # GDELT Events API - recent events with high impact
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": "economy OR sanctions OR military OR trade war OR tariff OR central bank",
                    "mode": "artlist",
                    "maxrecords": str(limit),
                    "format": "json",
                    "sort": "datedesc",
                    "timespan": "72h",
                },
                headers={"User-Agent": "Mozilla/5.0 (compatible; TradingAgents/1.0)"},
            )
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("articles", [])
                for art in articles[:limit]:
                    events.append({
                        "title": art.get("title", ""),
                        "url": art.get("url", ""),
                        "source": art.get("domain", ""),
                        "language": art.get("language", "English"),
                        "seendate": art.get("seendate", ""),
                        "socialimage": art.get("socialimage", ""),
                    })
    except Exception as e:
        logger.warning("GDELT events fetch failed: %s", e)

    _set_cached(cache_key, events)
    return events


# ── COMBINED FETCH ────────────────────────────────────────────────────────────

async def fetch_global_intel() -> dict:
    """Fetch all global intelligence data concurrently."""
    news_task = fetch_news_feeds("all")
    sentiment_task = fetch_market_sentiment()
    fred_task = fetch_fred_snapshot()
    gdelt_task = fetch_gdelt_events()

    news, sentiment, fred, gdelt = await asyncio.gather(
        news_task, sentiment_task, fred_task, gdelt_task,
        return_exceptions=True,
    )

    return {
        "news": news if isinstance(news, dict) else {},
        "sentiment": sentiment if isinstance(sentiment, dict) else {},
        "fred": fred if isinstance(fred, dict) else {},
        "gdelt": gdelt if isinstance(gdelt, list) else [],
        "fetched_at": datetime.now().strftime("%I:%M %p"),
    }
