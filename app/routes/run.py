"""Run route: trigger on-demand analysis runs."""

import logging
import threading
from datetime import date

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth, get_current_user
from app.database import get_db
from app.models import Run, RunDetail, Ticker, CostLog
from app.config import settings
from app.services.runner import run_analysis_sync

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _process_run_in_thread(run_id: int, symbol: str, trade_date: str):
    """Run analysis in a background thread using sync DB.

    Uses sync SQLAlchemy to avoid event-loop conflicts with
    run_analysis_sync, which needs its own asyncio.run() for Colonel Wolfe.
    """
    from sqlalchemy import create_engine, select as sa_select
    from sqlalchemy.orm import Session
    from app.config import settings as cfg

    sync_engine = create_engine(cfg.database_url_sync, pool_pre_ping=True)

    with Session(sync_engine) as db:
        run = db.get(Run, run_id)
        if not run or run.status != "pending":
            sync_engine.dispose()
            return

        run.status = "running"
        db.commit()

        try:
            logger.info("[worker] Starting analysis for %s (run %d)", symbol, run_id)
            state, decision, usage = run_analysis_sync(symbol, trade_date)

            # Save results synchronously
            from decimal import Decimal as D
            cost_usd = usage.get("cost_usd", D("0")) if usage else D("0")

            run.status = "complete"
            run.final_recommendation = decision
            from app.services.runner import extract_one_line_thesis, _to_str, extract_state_to_detail
            run.one_line_thesis = extract_one_line_thesis(
                _to_str(state.get("final_trade_decision", ""))
            )
            run.total_cost_usd = cost_usd
            run.model_used = cfg.deep_think_model
            db.commit()

            # Log cost
            if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
                try:
                    cost_entry = CostLog(
                        run_id=run.id,
                        provider="deepseek",
                        model=cfg.deep_think_model,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        cost_usd=cost_usd,
                    )
                    db.add(cost_entry)
                    db.commit()
                except Exception as e:
                    logger.error("[worker] Failed to log cost: %s", e)
                    db.rollback()

            # Save detail
            try:
                detail_fields = extract_state_to_detail(state)
                detail = RunDetail(run_id=run.id, **detail_fields)
                db.add(detail)
                db.commit()
            except Exception as e:
                logger.error("[worker] Failed to save RunDetail: %s", e)
                db.rollback()

            logger.info("[worker] Analysis complete for %s (run %d): %s", symbol, run_id, decision)

        except Exception as e:
            logger.error("[worker] Analysis failed for %s (run %d): %s", symbol, run_id, e)
            run.status = "failed"
            run.error_message = str(e)[:2000]
            db.commit()

    sync_engine.dispose()


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
    """Queue an on-demand analysis run and start processing."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    symbol = symbol.upper().strip()
    trade_date = date.today().strftime("%Y-%m-%d")

    # Create a pending run record
    run = Run(
        ticker_symbol=symbol,
        run_date=date.today(),
        status="pending",
        model_used=settings.deep_think_model,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Start background processing thread
    t = threading.Thread(
        target=_process_run_in_thread,
        args=(run.id, symbol, trade_date),
        daemon=True,
    )
    t.start()

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
    trade_date = date.today().strftime("%Y-%m-%d")

    run = Run(
        ticker_symbol=symbol,
        run_date=date.today(),
        status="pending",
        model_used=settings.deep_think_model,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Start background processing thread
    t = threading.Thread(
        target=_process_run_in_thread,
        args=(run.id, symbol, trade_date),
        daemon=True,
    )
    t.start()

    return JSONResponse({"status": "queued", "run_id": run.id, "symbol": symbol})


@router.post("/api/run/{run_id}/cancel")
async def api_cancel_run(
    request: Request,
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a stuck pending/running run."""
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    if run.status in ("pending", "running"):
        run.status = "failed"
        run.error_message = "Manually cancelled by user"
        await db.commit()
        return JSONResponse({"status": "cancelled", "run_id": run_id})

    return JSONResponse({"error": "Run is not cancellable", "status": run.status}, status_code=400)


@router.post("/run/{run_id}/cancel")
async def cancel_run_redirect(
    request: Request,
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a stuck run and redirect back to the run page."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run and run.status in ("pending", "running"):
        run.status = "failed"
        run.error_message = "Manually cancelled by user"
        await db.commit()

    return RedirectResponse(url="/run", status_code=303)
