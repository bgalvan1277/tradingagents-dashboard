"""History route: all runs across all tickers with filtering."""

from datetime import date, timedelta

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.database import get_db
from app.models import Run

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    ticker: str = Query(None),
    recommendation: str = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
):
    """Show history of all runs with optional filters."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Build query with filters
    query = select(Run).where(Run.status == "complete")

    if ticker:
        query = query.where(Run.ticker_symbol == ticker.upper())

    if recommendation:
        query = query.where(Run.final_recommendation == recommendation.capitalize())

    cutoff = date.today() - timedelta(days=days)
    query = query.where(Run.run_date >= cutoff)

    query = query.order_by(desc(Run.run_date), desc(Run.run_timestamp)).limit(200)

    result = await db.execute(query)
    runs = list(result.scalars().all())

    # Get unique tickers for filter dropdown
    ticker_query = select(Run.ticker_symbol).distinct().order_by(Run.ticker_symbol)
    ticker_result = await db.execute(ticker_query)
    available_tickers = [r[0] for r in ticker_result.all()]

    return templates.TemplateResponse(request, "history.html", context={
        "active_page": "history",
        "runs": runs,
        "available_tickers": available_tickers,
        "filter_ticker": ticker or "",
        "filter_recommendation": recommendation or "",
        "filter_days": days,
    })
