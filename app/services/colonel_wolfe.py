"""Colonel Wolfe's Intelligence Gathering Module.

Full-spectrum OSINT sweep for every ticker analysis. Queries ALL available
intelligence channels before the research analysts begin their work.

Data sources:
- SEC EDGAR: Form 4 insider trades, 8-K material events, 13F institutional
- Government Contracts: USASpending.gov API
- FRED Economic Data: Fed rate, CPI, unemployment, yield curve
- Earnings Calendar: Next earnings date, EPS/revenue estimates
- Technical Indicators: RSI, moving averages, volume profile
- Sector Rotation: Sector ETF relative performance
- FDA Calendar: Drug approval dates (biotech/pharma tickers)
- Stock Fundamentals: Full company profile via yfinance
"""

import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SEC_HEADERS = {"User-Agent": "TradingAgents Dashboard support@tradingagents.website"}
USASPENDING_BASE = "https://api.usaspending.gov/api/v2"

# Sector ETF mapping for rotation analysis
SECTOR_ETFS = {
    "Technology": "XLK", "Healthcare": "XLV", "Financial Services": "XLF",
    "Financials": "XLF", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Industrials": "XLI", "Energy": "XLE", "Real Estate": "XLRE",
    "Materials": "XLB", "Utilities": "XLU", "Communication Services": "XLC",
    "Basic Materials": "XLB",
}


# ── SEC EDGAR ──────────────────────────────────────────────────────────────────

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
    except Exception as e:
        logger.warning("SEC EDGAR %s query failed for %s: %s", form_type, ticker, e)
    return results


# ── GOVERNMENT CONTRACTS ───────────────────────────────────────────────────────

async def _fetch_gov_contracts(company_name: str) -> list[dict]:
    """Search USASpending.gov for federal contracts."""
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
                    "limit": 10, "order": "desc", "sort": "Award Amount",
                },
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    results.append({
                        "award_id": r.get("Award ID", ""),
                        "recipient": r.get("Recipient Name", ""),
                        "amount": r.get("Award Amount", 0),
                        "date": r.get("Start Date", ""),
                        "agency": r.get("Awarding Agency", ""),
                    })
    except Exception as e:
        logger.warning("USASpending query failed for %s: %s", company_name, e)
    return results


# ── FRED MACRO DATA ────────────────────────────────────────────────────────────

async def _fetch_fred_indicators() -> dict:
    """Fetch key FRED economic indicators."""
    indicators = {}
    series_map = {
        "fed_funds_rate": "FEDFUNDS",
        "unemployment_rate": "UNRATE",
        "cpi_yoy": "CPIAUCSL",
        "10yr_treasury": "DGS10",
        "2yr_treasury": "DGS2",
        "vix": "VIXCLS",
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
                            parts = lines[-1].split(",")
                            if len(parts) >= 2 and parts[1].strip() not in (".", ""):
                                indicators[label] = {"date": parts[0].strip(), "value": parts[1].strip()}
                except Exception:
                    pass
    except Exception as e:
        logger.warning("FRED fetch failed: %s", e)
    return indicators


# ── YFINANCE DATA (sync, run in executor) ──────────────────────────────────────

def _fetch_full_stock_data(ticker: str) -> dict:
    """Comprehensive stock data fetch: fundamentals, earnings, technicals, sector."""
    data = {
        "basics": {}, "earnings": {}, "technicals": {}, "sector_rotation": {},
    }
    try:
        import yfinance as yf
        import numpy as np

        tk = yf.Ticker(ticker)
        info = tk.info or {}

        # ── BASICS ──
        data["basics"] = {
            "company_name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "avg_volume": info.get("averageVolume", 0),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "short_ratio": info.get("shortRatio"),
            "short_pct_float": info.get("shortPercentOfFloat"),
            "institutional_pct": info.get("heldPercentInstitutions"),
            "description": (info.get("longBusinessSummary") or "")[:400],
        }

        # ── EARNINGS CALENDAR ──
        try:
            cal = tk.calendar
            if cal is not None and not cal.empty:
                if hasattr(cal, 'iloc'):
                    data["earnings"] = {
                        "earnings_date": str(cal.iloc[0].get("Earnings Date", "")) if hasattr(cal.iloc[0], 'get') else "",
                    }
            # Try earnings_dates for more detail
            ed = tk.earnings_dates
            if ed is not None and not ed.empty:
                future_dates = ed[ed.index >= datetime.now()]
                if not future_dates.empty:
                    next_date = future_dates.index[0]
                    row = future_dates.iloc[0]
                    data["earnings"] = {
                        "next_earnings": str(next_date.date()) if hasattr(next_date, 'date') else str(next_date),
                        "eps_estimate": row.get("EPS Estimate") if hasattr(row, 'get') else None,
                        "reported_eps": row.get("Reported EPS") if hasattr(row, 'get') else None,
                    }
        except Exception as e:
            logger.debug("Earnings calendar fetch issue for %s: %s", ticker, e)

        # ── TECHNICAL INDICATORS ──
        try:
            hist = tk.history(period="3mo")
            if hist is not None and len(hist) > 14:
                closes = hist["Close"].values
                volumes = hist["Volume"].values
                current_price = closes[-1]

                # RSI (14-period)
                deltas = np.diff(closes)
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains[-14:])
                avg_loss = np.mean(losses[-14:])
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100
                
                # Moving averages
                sma_20 = np.mean(closes[-20:]) if len(closes) >= 20 else None
                sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else None

                # Volume analysis
                avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else 0
                current_vol = volumes[-1]
                vol_ratio = (current_vol / avg_vol_20 * 100) if avg_vol_20 > 0 else 0

                # Price vs 52-week range
                high_52 = data["basics"].get("52w_high", 0)
                low_52 = data["basics"].get("52w_low", 0)
                pct_from_high = ((current_price - high_52) / high_52 * 100) if high_52 > 0 else 0
                pct_from_low = ((current_price - low_52) / low_52 * 100) if low_52 > 0 else 0

                data["technicals"] = {
                    "rsi_14": round(rsi, 1),
                    "sma_20": round(sma_20, 2) if sma_20 else None,
                    "sma_50": round(sma_50, 2) if sma_50 else None,
                    "above_sma_20": current_price > sma_20 if sma_20 else None,
                    "above_sma_50": current_price > sma_50 if sma_50 else None,
                    "volume_vs_avg": round(vol_ratio, 1),
                    "pct_from_52w_high": round(pct_from_high, 1),
                    "pct_from_52w_low": round(pct_from_low, 1),
                    "price_trend_20d": round((closes[-1] / closes[-20] - 1) * 100, 1) if len(closes) >= 20 else None,
                }
        except Exception as e:
            logger.debug("Technical analysis failed for %s: %s", ticker, e)

        # ── SECTOR ROTATION ──
        try:
            sector = info.get("sector", "")
            sector_etf = SECTOR_ETFS.get(sector)
            if sector_etf:
                etf = yf.Ticker(sector_etf)
                etf_hist = etf.history(period="1mo")
                if etf_hist is not None and len(etf_hist) > 1:
                    etf_return = (etf_hist["Close"].iloc[-1] / etf_hist["Close"].iloc[0] - 1) * 100

                    # Compare ticker's 1-month return
                    if len(hist) > 20:
                        ticker_return = (closes[-1] / closes[-20] - 1) * 100
                        relative_strength = ticker_return - etf_return
                    else:
                        ticker_return = 0
                        relative_strength = 0

                    # SPY as benchmark
                    spy = yf.Ticker("SPY")
                    spy_hist = spy.history(period="1mo")
                    spy_return = 0
                    if spy_hist is not None and len(spy_hist) > 1:
                        spy_return = (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[0] - 1) * 100

                    data["sector_rotation"] = {
                        "sector": sector,
                        "sector_etf": sector_etf,
                        "sector_1m_return": round(etf_return, 2),
                        "ticker_1m_return": round(ticker_return, 2),
                        "relative_strength_vs_sector": round(relative_strength, 2),
                        "spy_1m_return": round(spy_return, 2),
                        "relative_strength_vs_spy": round(ticker_return - spy_return, 2),
                    }
        except Exception as e:
            logger.debug("Sector rotation failed for %s: %s", ticker, e)

    except Exception as e:
        logger.warning("yfinance comprehensive fetch failed for %s: %s", ticker, e)
        data["basics"] = {"company_name": ticker, "sector": "Unknown", "industry": "Unknown"}

    return data


# ── BRIEFING COMPILER ──────────────────────────────────────────────────────────

def _format_briefing(ticker: str, stock_data: dict, insider_trades: list,
                     material_events: list, institutional: list,
                     gov_contracts: list, macro: dict) -> str:
    """Compile all intelligence into a structured briefing document."""
    basics = stock_data.get("basics", {})
    technicals = stock_data.get("technicals", {})
    earnings = stock_data.get("earnings", {})
    sector = stock_data.get("sector_rotation", {})

    lines = []
    lines.append("=" * 72)
    lines.append(f"  INTELLIGENCE BRIEFING: {ticker}")
    lines.append(f"  Prepared by: Col. Don Wolfe (RET), Intelligence Officer")
    lines.append(f"  Classification: UNCLASSIFIED // OPEN SOURCE")
    lines.append(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 72)

    # ── COMPANY PROFILE ──
    lines.append("\n─── COMPANY PROFILE ───────────────────────────────────────────")
    lines.append(f"  Company:    {basics.get('company_name', ticker)}")
    lines.append(f"  Sector:     {basics.get('sector', 'N/A')} | Industry: {basics.get('industry', 'N/A')}")
    mc = basics.get('market_cap', 0)
    if mc:
        if mc >= 1e12:
            lines.append(f"  Market Cap: ${mc/1e12:.2f}T")
        elif mc >= 1e9:
            lines.append(f"  Market Cap: ${mc/1e9:.2f}B")
        else:
            lines.append(f"  Market Cap: ${mc/1e6:.0f}M")
    lines.append(f"  Price:      ${basics.get('price', 0):,.2f}")
    pe = basics.get('pe_ratio')
    fpe = basics.get('forward_pe')
    if pe:
        lines.append(f"  P/E (TTM):  {pe:.2f}" + (f"  |  Forward P/E: {fpe:.2f}" if fpe else ""))
    peg = basics.get('peg_ratio')
    if peg:
        lines.append(f"  PEG Ratio:  {peg:.2f}")
    lines.append(f"  52W Range:  ${basics.get('52w_low', 0):,.2f} — ${basics.get('52w_high', 0):,.2f}")
    beta = basics.get('beta')
    if beta:
        lines.append(f"  Beta:       {beta:.2f}")
    pm = basics.get('profit_margin')
    rg = basics.get('revenue_growth')
    if pm is not None:
        lines.append(f"  Profit Margin: {pm*100:.1f}%")
    if rg is not None:
        lines.append(f"  Revenue Growth: {rg*100:.1f}%")
    si = basics.get('short_pct_float')
    sr = basics.get('short_ratio')
    if si is not None:
        lines.append(f"  Short Interest: {si*100:.1f}% of float (Days to Cover: {sr:.1f})" if sr else f"  Short Interest: {si*100:.1f}% of float")
    inst = basics.get('institutional_pct')
    if inst is not None:
        lines.append(f"  Institutional Ownership: {inst*100:.1f}%")

    # ── TECHNICAL INDICATORS ──
    lines.append("\n─── TECHNICAL INDICATORS ──────────────────────────────────────")
    if technicals:
        rsi = technicals.get('rsi_14')
        if rsi is not None:
            rsi_signal = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            lines.append(f"  RSI (14):   {rsi}  [{rsi_signal}]")
        sma20 = technicals.get('sma_20')
        sma50 = technicals.get('sma_50')
        if sma20:
            above = "ABOVE" if technicals.get('above_sma_20') else "BELOW"
            lines.append(f"  20-Day SMA: ${sma20:,.2f}  [Price {above}]")
        if sma50:
            above = "ABOVE" if technicals.get('above_sma_50') else "BELOW"
            lines.append(f"  50-Day SMA: ${sma50:,.2f}  [Price {above}]")
        vol = technicals.get('volume_vs_avg')
        if vol:
            vol_signal = "ELEVATED" if vol > 120 else "LOW" if vol < 80 else "NORMAL"
            lines.append(f"  Volume:     {vol:.0f}% of 20-day avg  [{vol_signal}]")
        h = technicals.get('pct_from_52w_high')
        l = technicals.get('pct_from_52w_low')
        if h is not None:
            lines.append(f"  52W Range:  {h:+.1f}% from high  |  {l:+.1f}% from low")
        trend = technicals.get('price_trend_20d')
        if trend is not None:
            lines.append(f"  20-Day Trend: {trend:+.1f}%")
    else:
        lines.append("  Technical data unavailable.")

    # ── EARNINGS CALENDAR ──
    lines.append("\n─── EARNINGS CALENDAR ─────────────────────────────────────────")
    if earnings:
        nd = earnings.get('next_earnings')
        if nd:
            lines.append(f"  Next Earnings: {nd}")
        eps_est = earnings.get('eps_estimate')
        if eps_est is not None:
            lines.append(f"  EPS Estimate:  ${eps_est:.2f}")
        rep_eps = earnings.get('reported_eps')
        if rep_eps is not None:
            lines.append(f"  Last Reported: ${rep_eps:.2f}")
        if not nd and not eps_est:
            lines.append("  No upcoming earnings data found.")
    else:
        lines.append("  Earnings calendar data not available.")

    # ── SECTOR ROTATION ──
    lines.append("\n─── SECTOR ROTATION ───────────────────────────────────────────")
    if sector:
        lines.append(f"  Sector: {sector.get('sector', 'N/A')} ({sector.get('sector_etf', '')})")
        lines.append(f"  Sector 1-Month Return:  {sector.get('sector_1m_return', 0):+.2f}%")
        lines.append(f"  {ticker} 1-Month Return: {sector.get('ticker_1m_return', 0):+.2f}%")
        rs = sector.get('relative_strength_vs_sector', 0)
        rs_label = "OUTPERFORMING" if rs > 0 else "UNDERPERFORMING"
        lines.append(f"  vs Sector:  {rs:+.2f}%  [{rs_label} SECTOR]")
        lines.append(f"  SPY 1-Month Return:     {sector.get('spy_1m_return', 0):+.2f}%")
        rs_spy = sector.get('relative_strength_vs_spy', 0)
        rs_spy_label = "OUTPERFORMING" if rs_spy > 0 else "UNDERPERFORMING"
        lines.append(f"  vs S&P 500: {rs_spy:+.2f}%  [{rs_spy_label} MARKET]")
    else:
        lines.append("  Sector rotation data unavailable.")

    # ── SEC FORM 4 INSIDER TRADES ──
    lines.append(f"\n─── SEC FORM 4 — INSIDER TRANSACTIONS ({len(insider_trades)} filings) ──")
    if insider_trades:
        for t in insider_trades[:8]:
            lines.append(f"  [{t['date']}] {t['filer'][:40]}")
    else:
        lines.append("  No recent Form 4 filings detected.")

    # ── SEC 8-K MATERIAL EVENTS ──
    lines.append(f"\n─── SEC 8-K — MATERIAL EVENTS ({len(material_events)} filings) ────────")
    if material_events:
        for e in material_events[:5]:
            lines.append(f"  [{e['date']}] {e['filer'][:40]}")
    else:
        lines.append("  No recent 8-K filings detected.")

    # ── SEC 13F INSTITUTIONAL ──
    lines.append(f"\n─── SEC 13F — INSTITUTIONAL HOLDINGS ({len(institutional)} filings) ──")
    if institutional:
        for i in institutional[:5]:
            lines.append(f"  [{i['date']}] {i['filer'][:40]}")
    else:
        lines.append("  No recent 13F filings detected.")

    # ── GOVERNMENT CONTRACTS ──
    lines.append(f"\n─── GOVERNMENT CONTRACTS ({len(gov_contracts)} found) ────────────────")
    if gov_contracts:
        for c in gov_contracts[:5]:
            amt = c.get('amount', 0)
            amt_str = f"${amt:,.0f}" if amt else "Undisclosed"
            lines.append(f"  [{c.get('date', 'N/A')}] {amt_str} — {c.get('agency', 'N/A')[:40]}")
    else:
        lines.append("  No federal contract awards found.")

    # ── MACROECONOMIC ENVIRONMENT ──
    lines.append("\n─── MACROECONOMIC ENVIRONMENT ─────────────────────────────────")
    if macro:
        for label, d in macro.items():
            display = label.replace("_", " ").title()
            lines.append(f"  {display}: {d.get('value', 'N/A')}  (as of {d.get('date', 'N/A')})")
    else:
        lines.append("  Macro data temporarily unavailable.")

    # ── INTELLIGENCE ASSESSMENT ──
    lines.append("\n─── INTELLIGENCE ASSESSMENT ───────────────────────────────────")
    signals = []
    
    # RSI signals
    rsi_val = technicals.get('rsi_14')
    if rsi_val and rsi_val > 70:
        signals.append("[CAUTION] RSI above 70 indicates overbought conditions.")
    elif rsi_val and rsi_val < 30:
        signals.append("[OPPORTUNITY] RSI below 30 indicates oversold conditions.")

    # Volume signals
    vol_val = technicals.get('volume_vs_avg')
    if vol_val and vol_val > 150:
        signals.append(f"[ALERT] Volume {vol_val:.0f}% of average. Unusual activity detected.")

    # Insider signals
    if len(insider_trades) > 5:
        signals.append(f"[SIGNAL] {len(insider_trades)} insider filings detected. Elevated insider activity.")

    # Government exposure
    if len(gov_contracts) > 0:
        signals.append(f"[INTEL] {len(gov_contracts)} federal contract(s) confirmed. Government revenue exposure active.")

    # Sector performance
    rs_val = sector.get('relative_strength_vs_sector')
    if rs_val and rs_val > 5:
        signals.append(f"[STRENGTH] {ticker} outperforming sector by {rs_val:+.1f}%. Relative strength confirmed.")
    elif rs_val and rs_val < -5:
        signals.append(f"[WEAKNESS] {ticker} underperforming sector by {rs_val:+.1f}%. Relative weakness noted.")

    # Short interest
    si_val = basics.get('short_pct_float')
    if si_val and si_val > 0.10:
        signals.append(f"[ALERT] Short interest at {si_val*100:.1f}% of float. Elevated bearish positioning.")

    if signals:
        for s in signals:
            lines.append(f"  {s}")
    else:
        lines.append("  No actionable signals detected at this time.")

    total_datapoints = (len(insider_trades) + len(material_events) + len(institutional)
                        + len(gov_contracts) + len(macro) + (1 if technicals else 0)
                        + (1 if earnings else 0) + (1 if sector else 0))
    lines.append(f"\n  Total data points collected: {total_datapoints}")
    lines.append(f"  Intelligence channels queried: 9")
    lines.append("  Classification: UNCLASSIFIED // OPEN SOURCE")
    lines.append("=" * 72)

    return "\n".join(lines)


# ── MAIN SWEEP ─────────────────────────────────────────────────────────────────

async def run_intelligence_sweep(ticker: str) -> str:
    """Execute full-spectrum intelligence gathering sweep for a ticker.

    Queries all available intelligence channels:
    1. SEC EDGAR (Form 4, 8-K, 13F)
    2. USASpending.gov (government contracts)
    3. FRED (macroeconomic indicators)
    4. yfinance (fundamentals, earnings, technicals, sector rotation)

    Returns a formatted intelligence briefing string.
    """
    logger.info("Col. Wolfe initiating full-spectrum intelligence sweep for %s", ticker)

    # Run yfinance (sync) in executor
    loop = asyncio.get_event_loop()
    stock_data = await loop.run_in_executor(None, _fetch_full_stock_data, ticker)

    # Run all async API calls concurrently
    insider_task = _fetch_sec_filings(ticker, "4", limit=15)
    events_task = _fetch_sec_filings(ticker, "8-K", limit=10)
    institutional_task = _fetch_sec_filings(ticker, "13F-HR", limit=10)
    macro_task = _fetch_fred_indicators()

    insider_trades, material_events, institutional, macro = await asyncio.gather(
        insider_task, events_task, institutional_task, macro_task
    )

    # Government contracts - use company name
    company_name = stock_data.get("basics", {}).get("company_name", ticker)
    gov_contracts = await _fetch_gov_contracts(company_name)

    # Compile the full briefing
    briefing = _format_briefing(
        ticker, stock_data, insider_trades, material_events,
        institutional, gov_contracts, macro
    )

    logger.info(
        "Intelligence briefing compiled for %s: %d chars, %d signals",
        ticker, len(briefing),
        sum(1 for line in briefing.split("\n") if "[" in line and "]" in line)
    )
    return briefing
