"""Colonel Wolfe's Intelligence Gathering Module.

This module runs BEFORE the TradingAgents pipeline, collecting OSINT data from
all available intelligence sources for a specific ticker. The compiled briefing
is injected into the agent state so every downstream analyst has access to
the intelligence findings.

Data sources queried:
- SEC EDGAR: Form 4 insider trades, 8-K material events, 13F holdings
- Government Contracts: USASpending.gov API for federal award data
- FRED Economic Data: Key macro indicators (Fed rate, CPI, unemployment)
- Stock Fundamentals: yfinance for price, volume, sector classification
"""

import logging
import httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SEC_HEADERS = {"User-Agent": "TradingAgents Dashboard support@tradingagents.website"}
USASPENDING_BASE = "https://api.usaspending.gov/api/v2"


async def _fetch_sec_filings(ticker: str, form_type: str = "4", limit: int = 10) -> list[dict]:
    """Fetch recent SEC filings for a specific company ticker."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": ticker, "forms": form_type, "dateRange": "custom", "startdt": "2025-01-01"},
                headers=SEC_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for h in hits[:limit]:
                    src = h.get("_source", {})
                    names = src.get("display_names", [])
                    results.append({
                        "date": src.get("file_date", ""),
                        "filer": names[0].split("(CIK")[0].strip() if names else "Unknown",
                        "company": names[1].split("(CIK")[0].strip() if len(names) > 1 else "",
                        "form": form_type,
                        "filing_id": src.get("adsh", ""),
                    })
                logger.info("SEC EDGAR: Found %d %s filings for %s", len(results), form_type, ticker)
    except Exception as e:
        logger.warning("SEC EDGAR query failed for %s: %s", ticker, e)
    return results


async def _fetch_gov_contracts(company_name: str) -> list[dict]:
    """Search USASpending.gov for federal contracts awarded to a company."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{USASPENDING_BASE}/search/spending_by_award/",
                json={
                    "filters": {
                        "keyword": company_name,
                        "time_period": [{"start_date": "2024-01-01", "end_date": datetime.now().strftime("%Y-%m-%d")}],
                    },
                    "fields": ["Award ID", "Recipient Name", "Award Amount", "Start Date", "Awarding Agency"],
                    "limit": 10,
                    "order": "desc",
                    "sort": "Award Amount",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                for r in data.get("results", []):
                    results.append({
                        "award_id": r.get("Award ID", ""),
                        "recipient": r.get("Recipient Name", ""),
                        "amount": r.get("Award Amount", 0),
                        "date": r.get("Start Date", ""),
                        "agency": r.get("Awarding Agency", ""),
                    })
                logger.info("USASpending: Found %d contracts for %s", len(results), company_name)
    except Exception as e:
        logger.warning("USASpending query failed for %s: %s", company_name, e)
    return results


async def _fetch_fred_indicators() -> dict:
    """Fetch key FRED economic indicators (no API key needed for basic access)."""
    indicators = {}
    series_map = {
        "fed_rate": "FEDFUNDS",
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "ten_year_yield": "DGS10",
        "two_year_yield": "DGS2",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for label, series_id in series_map.items():
                try:
                    resp = await client.get(
                        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                        headers={"User-Agent": "TradingAgents/1.0"},
                    )
                    if resp.status_code == 200:
                        lines = resp.text.strip().split("\n")
                        if len(lines) > 1:
                            last_line = lines[-1]
                            parts = last_line.split(",")
                            if len(parts) >= 2 and parts[1].strip() != ".":
                                indicators[label] = {
                                    "date": parts[0].strip(),
                                    "value": parts[1].strip(),
                                }
                except Exception:
                    pass
    except Exception as e:
        logger.warning("FRED indicators fetch failed: %s", e)
    return indicators


async def _fetch_stock_basics(ticker: str) -> dict:
    """Fetch basic stock info from yfinance."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        return {
            "company_name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "pe_ratio": info.get("trailingPE", None),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "avg_volume": info.get("averageVolume", 0),
            "description": (info.get("longBusinessSummary") or "")[:500],
        }
    except Exception as e:
        logger.warning("yfinance lookup failed for %s: %s", ticker, e)
        return {"company_name": ticker, "sector": "Unknown", "industry": "Unknown"}


def _format_briefing(ticker: str, basics: dict, insider_trades: list,
                     material_events: list, gov_contracts: list,
                     macro: dict) -> str:
    """Compile all intelligence into a structured briefing document."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"INTELLIGENCE BRIEFING: {ticker}")
    lines.append(f"Prepared by: Col. Don Wolfe (RET), Intelligence Officer")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 70)

    # Company Profile
    lines.append("\n## COMPANY PROFILE")
    lines.append(f"Company: {basics.get('company_name', ticker)}")
    lines.append(f"Sector: {basics.get('sector', 'N/A')} | Industry: {basics.get('industry', 'N/A')}")
    mc = basics.get('market_cap', 0)
    if mc:
        lines.append(f"Market Cap: ${mc:,.0f}")
    lines.append(f"Current Price: ${basics.get('price', 0):,.2f}")
    pe = basics.get('pe_ratio')
    if pe:
        lines.append(f"P/E Ratio: {pe:.2f}")
    lines.append(f"52-Week Range: ${basics.get('52w_low', 0):,.2f} - ${basics.get('52w_high', 0):,.2f}")

    # Insider Activity
    lines.append(f"\n## SEC FORM 4 - INSIDER TRANSACTIONS ({len(insider_trades)} recent filings)")
    if insider_trades:
        for t in insider_trades[:10]:
            lines.append(f"  [{t['date']}] {t['filer']} - {t.get('company', '')} (Filing: {t['filing_id'][:20]})")
    else:
        lines.append("  No recent Form 4 filings detected for this ticker.")

    # Material Events
    lines.append(f"\n## SEC 8-K - MATERIAL EVENTS ({len(material_events)} recent filings)")
    if material_events:
        for e in material_events[:5]:
            lines.append(f"  [{e['date']}] {e['filer']} - {e.get('company', '')} (Filing: {e['filing_id'][:20]})")
    else:
        lines.append("  No recent 8-K filings detected for this ticker.")

    # Government Contracts
    lines.append(f"\n## GOVERNMENT CONTRACTS ({len(gov_contracts)} found)")
    if gov_contracts:
        for c in gov_contracts[:5]:
            amt = c.get('amount', 0)
            amt_str = f"${amt:,.0f}" if amt else "Undisclosed"
            lines.append(f"  [{c.get('date', 'N/A')}] {c.get('recipient', '')} - {amt_str} via {c.get('agency', 'N/A')}")
    else:
        lines.append("  No federal contract awards found for this company.")

    # Macro Environment
    lines.append("\n## MACROECONOMIC ENVIRONMENT")
    if macro:
        for label, data in macro.items():
            display = label.replace("_", " ").title()
            lines.append(f"  {display}: {data.get('value', 'N/A')} (as of {data.get('date', 'N/A')})")
    else:
        lines.append("  Macro data temporarily unavailable.")

    # Assessment
    lines.append("\n## INTELLIGENCE ASSESSMENT")
    insider_count = len(insider_trades)
    event_count = len(material_events)
    contract_count = len(gov_contracts)

    if insider_count > 5:
        lines.append("  [SIGNAL] High insider transaction volume detected. Recommend close scrutiny of buy/sell ratio.")
    if event_count > 3:
        lines.append("  [SIGNAL] Elevated material event filings. Company may be undergoing significant corporate action.")
    if contract_count > 0:
        lines.append(f"  [SIGNAL] {contract_count} federal contract(s) identified. Government revenue exposure confirmed.")

    lines.append(f"\n  Total data points collected: {insider_count + event_count + contract_count + len(macro)}")
    lines.append("  Classification: UNCLASSIFIED // OPEN SOURCE")
    lines.append("=" * 70)

    return "\n".join(lines)


async def run_intelligence_sweep(ticker: str) -> str:
    """Execute full intelligence gathering sweep for a ticker.

    This is the main entry point called by the analysis pipeline.
    Returns a formatted intelligence briefing string.
    """
    logger.info("Col. Wolfe initiating intelligence sweep for %s", ticker)

    # Gather all data concurrently
    import asyncio
    basics_task = _fetch_stock_basics(ticker)
    insider_task = _fetch_sec_filings(ticker, "4", limit=15)
    events_task = _fetch_sec_filings(ticker, "8-K", limit=10)
    macro_task = _fetch_fred_indicators()

    # yfinance is sync, run it in executor
    loop = asyncio.get_event_loop()
    basics = await loop.run_in_executor(None, lambda: asyncio.run(_run_sync_basics(ticker)))

    # Run async tasks
    insider_trades, material_events, macro = await asyncio.gather(
        insider_task, events_task, macro_task
    )

    # Government contracts - use company name from basics
    company_name = basics.get("company_name", ticker)
    gov_contracts = await _fetch_gov_contracts(company_name)

    # Compile briefing
    briefing = _format_briefing(
        ticker, basics, insider_trades, material_events, gov_contracts, macro
    )

    logger.info("Intelligence briefing compiled for %s: %d chars", ticker, len(briefing))
    return briefing


async def _run_sync_basics(ticker: str) -> dict:
    """Helper to run sync yfinance in async context."""
    return await asyncio.sleep(0) or _fetch_stock_basics_sync(ticker)


def _fetch_stock_basics_sync(ticker: str) -> dict:
    """Synchronous version of stock basics fetch."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        return {
            "company_name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "pe_ratio": info.get("trailingPE", None),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "avg_volume": info.get("averageVolume", 0),
            "description": (info.get("longBusinessSummary") or "")[:500],
        }
    except Exception as e:
        logger.warning("yfinance sync failed for %s: %s", ticker, e)
        return {"company_name": ticker, "sector": "Unknown", "industry": "Unknown"}


import asyncio
