"""Ticker detail route: full analysis view for a single ticker."""

import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_auth
from app.database import get_db
from app.models import Run, RunDetail

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _get_stock_quote(symbol: str) -> dict:
    """Fetch live stock data from yfinance. Returns empty dict on failure."""
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)
        info = tk.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose") or 0
        change = round(price - prev, 2) if price and prev else 0
        pct = round((change / prev) * 100, 2) if prev else 0
        return {
            "company_name": info.get("shortName") or info.get("longName") or symbol,
            "price": round(price, 2),
            "change": change,
            "change_pct": pct,
            "currency": info.get("currency", "USD"),
            "market_state": info.get("marketState", ""),
        }
    except Exception as e:
        logger.warning("yfinance lookup failed for %s: %s", symbol, e)
        return {}


@router.get("/api/quote/{symbol}")
async def api_quote(request: Request, symbol: str):
    """JSON API: return live quote data for a ticker."""
    redirect = require_auth(request)
    if redirect:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = _get_stock_quote(symbol.upper())
    if not data:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not found"}, status_code=404)
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "name": data.get("company_name", symbol),
        "price": data.get("price", 0),
        "change": data.get("change", 0),
        "pct": data.get("change_pct", 0),
    })


@router.get("/ticker/{symbol}", response_class=HTMLResponse)
async def ticker_detail(
    request: Request,
    symbol: str,
    run_id: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Show the full analysis for a ticker's most recent (or specified) run."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    symbol = symbol.upper()

    # Fetch live stock quote
    quote = _get_stock_quote(symbol)

    # Get the specific run or the latest one
    if run_id:
        run_query = (
            select(Run)
            .where(Run.id == run_id, Run.ticker_symbol == symbol)
        )
    else:
        run_query = (
            select(Run)
            .where(Run.ticker_symbol == symbol, Run.status == "complete")
            .order_by(desc(Run.run_date), desc(Run.run_timestamp))
            .limit(1)
        )

    run_result = await db.execute(run_query)
    run = run_result.scalar_one_or_none()

    # Get run details if run exists
    details = None
    if run:
        details_query = select(RunDetail).where(RunDetail.run_id == run.id)
        details_result = await db.execute(details_query)
        details = details_result.scalar_one_or_none()

    # Get past runs for the history table
    past_runs_query = (
        select(Run)
        .where(Run.ticker_symbol == symbol, Run.status == "complete")
        .order_by(desc(Run.run_date), desc(Run.run_timestamp))
        .limit(30)
    )
    past_runs_result = await db.execute(past_runs_query)
    past_runs = list(past_runs_result.scalars().all())

    # Exclude the current run from past runs
    if run:
        past_runs = [r for r in past_runs if r.id != run.id]

    return templates.TemplateResponse(request, "ticker_detail.html", context={
        "ticker_symbol": symbol,
        "quote": quote,
        "run": run,
        "details": details,
        "past_runs": past_runs,
    })
