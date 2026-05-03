"""Day Trade Briefing routes.

Provides a day-trade screener and individual trade plan briefings.
Two views:
  GET  /briefing         - Screener + ticker input form
  POST /briefing         - Generate trade plan for a ticker
  POST /briefing/screen  - Run screener on multiple tickers
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth, get_current_user
from app.database import get_db
from app.models import Ticker
from app.services.briefing import generate_trade_plan, screen_tickers

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Default screener tickers (popular day-trade names)
DEFAULT_SCREEN_TICKERS = [
    "NVDA", "TSLA", "AMD", "AAPL", "AMZN", "META", "PLTR", "SOUN",
    "SOFI", "NIO", "RIVN", "MARA", "COIN", "SPY", "QQQ",
]


@router.get("/briefing", response_class=HTMLResponse)
async def briefing_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Show the day-trade screener and briefing input page."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Get watchlist tickers for the dropdown
    tickers_result = await db.execute(
        select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
    )
    watchlist = list(tickers_result.scalars().all())

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
    })


@router.post("/briefing", response_class=HTMLResponse)
async def generate_briefing(
    request: Request,
    ticker: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Generate a day-trade briefing for a specific ticker."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    ticker = ticker.upper().strip()

    # Get watchlist for sidebar context
    tickers_result = await db.execute(
        select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
    )
    watchlist = list(tickers_result.scalars().all())

    # Generate the trade plan
    trade_plan = await generate_trade_plan(ticker)

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "trade_plan": trade_plan,
        "selected_ticker": ticker,
    })


@router.post("/briefing/screen", response_class=HTMLResponse)
async def run_screener(
    request: Request,
    tickers: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Run the day-trade screener on a list of tickers."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Parse ticker list from form
    if tickers.strip():
        symbols = [t.strip().upper() for t in tickers.replace(",", " ").split() if t.strip()]
    else:
        # Default: use watchlist + popular tickers
        tickers_result = await db.execute(
            select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
        )
        watchlist = list(tickers_result.scalars().all())
        symbols = [t.symbol for t in watchlist] + DEFAULT_SCREEN_TICKERS
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        symbols = unique

    # Score all tickers
    scored = await screen_tickers(symbols)

    # Get watchlist for the form
    tickers_result = await db.execute(
        select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
    )
    watchlist = list(tickers_result.scalars().all())

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "screener_results": scored,
        "screener_count": len(scored),
    })


@router.get("/api/briefing/{ticker}")
async def api_generate_briefing(request: Request, ticker: str):
    """API endpoint to generate a briefing (for HTMX or fetch calls)."""
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    ticker = ticker.upper().strip()
    trade_plan = await generate_trade_plan(ticker)

    if trade_plan.get("error"):
        return JSONResponse({"error": trade_plan["error"]}, status_code=500)

    # Remove the raw briefing from API response (too large)
    plan_copy = {k: v for k, v in trade_plan.items() if k != "briefing"}
    return JSONResponse(plan_copy)
