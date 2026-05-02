"""Ticker detail route: full analysis view for a single ticker."""

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

    return templates.TemplateResponse("ticker_detail.html", {
        "request": request,
        "ticker_symbol": symbol,
        "run": run,
        "details": details,
        "past_runs": past_runs,
    })
