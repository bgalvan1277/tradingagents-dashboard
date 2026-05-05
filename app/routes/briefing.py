"""Day Trade Briefing routes.

Provides a day-trade screener and individual trade plan briefings.
Plans are persisted to the database for historical review.

Routes:
  GET  /briefing              - Screener + ticker input + history
  POST /briefing              - Generate trade plan for a ticker
  POST /briefing/screen       - Run screener on multiple tickers
  GET  /briefing/history      - View all saved trade plans
  GET  /briefing/plan/{id}    - View a specific saved plan
  GET  /api/briefing/{ticker} - API: generate briefing (JSON)
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth, get_current_user
from app.database import get_db
from app.models import Ticker, TradePlan
from app.services.briefing import generate_trade_plan, screen_tickers

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Default screener tickers (popular day-trade names)
DEFAULT_SCREEN_TICKERS = [
    "NVDA", "TSLA", "AMD", "AAPL", "AMZN", "META", "PLTR", "SOUN",
    "SOFI", "NIO", "RIVN", "MARA", "COIN", "SPY", "QQQ",
]


async def _save_trade_plan(db: AsyncSession, plan: dict) -> int | None:
    """Persist a trade plan to the database. Returns the new plan ID."""
    if plan.get("error"):
        return None
    try:
        # Remove briefing text from stored JSON (too large)
        plan_data = {k: v for k, v in plan.items() if k != "briefing"}
        entry = TradePlan(
            ticker_symbol=plan.get("ticker", "???"),
            direction=plan.get("direction", "NO TRADE"),
            confidence=plan.get("confidence", 0),
            thesis=plan.get("thesis", ""),
            plan_json=plan_data,
            cost_usd=Decimal(str(plan.get("cost_usd", 0))),
            tokens_used=plan.get("tokens_used", 0),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        logger.info("Saved trade plan #%d for %s", entry.id, entry.ticker_symbol)
        return entry.id
    except Exception as e:
        logger.warning("Failed to save trade plan: %s", e)
        return None


async def _get_recent_plans(db: AsyncSession, limit: int = 20) -> list:
    """Fetch recent trade plans from the database."""
    try:
        result = await db.execute(
            select(TradePlan)
            .order_by(desc(TradePlan.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    except Exception as e:
        logger.warning("Failed to load trade plan history: %s", e)
        return []


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

    # Get recent trade plan history
    history = await _get_recent_plans(db)

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "history": history,
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

    # Save to database
    plan_id = await _save_trade_plan(db, trade_plan)
    if plan_id:
        trade_plan["plan_id"] = plan_id

    # Get recent history
    history = await _get_recent_plans(db)

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "trade_plan": trade_plan,
        "selected_ticker": ticker,
        "history": history,
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

    # Get recent history
    history = await _get_recent_plans(db)

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "screener_results": scored,
        "screener_count": len(scored),
        "history": history,
    })


@router.get("/briefing/plan/{plan_id}", response_class=HTMLResponse)
async def view_saved_plan(
    request: Request,
    plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """View a previously saved trade plan."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Load the plan
    result = await db.execute(select(TradePlan).where(TradePlan.id == plan_id))
    plan_entry = result.scalar_one_or_none()

    if not plan_entry:
        return RedirectResponse("/briefing", status_code=302)

    # Reconstruct the trade_plan dict from stored JSON
    trade_plan = plan_entry.plan_json or {}
    trade_plan["ticker"] = plan_entry.ticker_symbol
    trade_plan["direction"] = plan_entry.direction
    trade_plan["confidence"] = plan_entry.confidence
    trade_plan["thesis"] = plan_entry.thesis
    trade_plan["generated_at"] = plan_entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
    trade_plan["plan_id"] = plan_entry.id
    trade_plan["is_historical"] = True

    # Get watchlist and history
    tickers_result = await db.execute(
        select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
    )
    watchlist = list(tickers_result.scalars().all())
    history = await _get_recent_plans(db)

    return templates.TemplateResponse(request, "briefing.html", context={
        "active_page": "briefing",
        "watchlist": watchlist,
        "default_tickers": DEFAULT_SCREEN_TICKERS,
        "now": datetime.now(),
        "trade_plan": trade_plan,
        "selected_ticker": plan_entry.ticker_symbol,
        "history": history,
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
