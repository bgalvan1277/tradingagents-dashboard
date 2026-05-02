"""Run route: trigger on-demand analysis runs."""

from datetime import date

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth, get_current_user
from app.database import get_db
from app.models import Run, Ticker
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/run", response_class=HTMLResponse)
async def run_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Show the run management page with queue status."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Get active tickers for the dropdown
    tickers_result = await db.execute(
        select(Ticker).where(Ticker.active == True).order_by(Ticker.symbol)
    )
    tickers = list(tickers_result.scalars().all())

    # Get pending/running runs
    queue_result = await db.execute(
        select(Run)
        .where(Run.status.in_(["pending", "running"]))
        .order_by(desc(Run.created_at))
    )
    queue = list(queue_result.scalars().all())

    # Get recent completed runs (last 10)
    recent_result = await db.execute(
        select(Run)
        .where(Run.status.in_(["complete", "failed"]))
        .order_by(desc(Run.run_timestamp))
        .limit(10)
    )
    recent = list(recent_result.scalars().all())

    return templates.TemplateResponse(request, "run.html", context={
        "active_page": "run",
        "tickers": tickers,
        "queue": queue,
        "recent": recent,
    })


@router.post("/run/submit", response_class=HTMLResponse)
async def submit_run(
    request: Request,
    symbol: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Queue an on-demand analysis run."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    symbol = symbol.upper().strip()

    # Create a pending run record (the worker will pick it up)
    run = Run(
        ticker_symbol=symbol,
        run_date=date.today(),
        status="pending",
        model_used=settings.deep_think_model,
    )
    db.add(run)
    await db.commit()

    return RedirectResponse(url="/run", status_code=303)


@router.post("/api/run/{symbol}")
async def api_trigger_run(
    request: Request,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """API endpoint to trigger a run (used by HTMX on ticker detail page)."""
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    symbol = symbol.upper().strip()

    run = Run(
        ticker_symbol=symbol,
        run_date=date.today(),
        status="pending",
        model_used=settings.deep_think_model,
    )
    db.add(run)
    await db.commit()

    return JSONResponse({"status": "queued", "run_id": run.id, "symbol": symbol})
