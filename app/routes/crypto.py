"""Crypto Analyzer route: crypto-only portfolio view."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.database import get_db
from app.models import Run, Ticker, WatchlistEntry, CostLog

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/crypto", response_class=HTMLResponse)
async def crypto_analyzer(request: Request, db: AsyncSession = Depends(get_db)):
    """Show crypto-only portfolio with latest run per crypto ticker."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Get active watchlist tickers in the crypto group
    watchlist_query = (
        select(Ticker, WatchlistEntry)
        .join(WatchlistEntry, WatchlistEntry.ticker_id == Ticker.id)
        .where(Ticker.active == True)
        .where(WatchlistEntry.group_name == "crypto")
        .order_by(WatchlistEntry.position)
    )
    result = await db.execute(watchlist_query)
    watchlist_items = result.all()

    # Get the latest run for each ticker
    runs = []
    for ticker, wl_entry in watchlist_items:
        run_query = (
            select(Run)
            .where(Run.ticker_symbol == ticker.symbol)
            .order_by(desc(Run.run_date), desc(Run.run_timestamp))
            .limit(1)
        )
        run_result = await db.execute(run_query)
        run = run_result.scalar_one_or_none()

        if run:
            runs.append(run)
        else:
            placeholder = Run(
                ticker_symbol=ticker.symbol,
                run_date=date.today(),
                status="pending",
            )
            runs.append(placeholder)

    # Calculate daily cost
    today = date.today()
    cost_query = select(func.sum(CostLog.cost_usd)).where(
        func.date(CostLog.timestamp) == today
    )
    cost_result = await db.execute(cost_query)
    daily_cost = cost_result.scalar() or Decimal("0")

    return templates.TemplateResponse(request, "crypto.html", context={
        "runs": runs,
        "current_date": today.strftime("%A, %B %d, %Y"),
        "daily_cost": float(daily_cost),
    })
