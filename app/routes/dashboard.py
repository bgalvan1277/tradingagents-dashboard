"""Dashboard route: main page showing latest run per ticker."""

from datetime import date, datetime
from decimal import Decimal
from collections import OrderedDict

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.database import get_db
from app.models import Run, Ticker, WatchlistEntry, CostLog
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Show the main dashboard with latest run per watchlist ticker."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Get all active watchlist tickers with their group info
    watchlist_query = (
        select(Ticker, WatchlistEntry)
        .join(WatchlistEntry, WatchlistEntry.ticker_id == Ticker.id)
        .where(Ticker.active == True)
        .order_by(WatchlistEntry.group_name, WatchlistEntry.position)
    )
    result = await db.execute(watchlist_query)
    watchlist_items = result.all()

    # Get the latest completed run for each ticker
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
            run._group_name = wl_entry.group_name if wl_entry else "default"
            runs.append(run)
        else:
            # Create a placeholder for tickers with no runs yet
            placeholder = Run(
                ticker_symbol=ticker.symbol,
                run_date=date.today(),
                status="pending",
            )
            placeholder._group_name = wl_entry.group_name if wl_entry else "default"
            runs.append(placeholder)

    # Group runs by watchlist group
    grouped_runs = OrderedDict()
    for run in runs:
        group = getattr(run, '_group_name', 'default')
        if group not in grouped_runs:
            grouped_runs[group] = []
        grouped_runs[group].append(run)

    # Calculate daily cost
    today = date.today()
    cost_query = select(func.sum(CostLog.cost_usd)).where(
        func.date(CostLog.timestamp) == today
    )
    cost_result = await db.execute(cost_query)
    daily_cost = cost_result.scalar() or Decimal("0")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "runs": runs,
        "grouped_runs": grouped_runs if len(grouped_runs) > 1 else None,
        "current_date": today.strftime("%A, %B %d, %Y"),
        "daily_cost": float(daily_cost),
        "daily_cap": float(settings.daily_cost_cap_usd),
    })
