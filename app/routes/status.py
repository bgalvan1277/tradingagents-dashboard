"""System status route: API spend, cron health, recent failures."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.database import get_db
from app.models import Run, CostLog, CronLog
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Show system status: costs, cron health, recent failures."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    today = date.today()
    month_start = today.replace(day=1)

    # Daily cost
    daily_cost_result = await db.execute(
        select(func.sum(CostLog.cost_usd)).where(func.date(CostLog.timestamp) == today)
    )
    daily_cost = daily_cost_result.scalar() or Decimal("0")

    # Monthly cost
    monthly_cost_result = await db.execute(
        select(func.sum(CostLog.cost_usd)).where(CostLog.timestamp >= datetime.combine(month_start, datetime.min.time()))
    )
    monthly_cost = monthly_cost_result.scalar() or Decimal("0")

    # Daily token usage
    daily_tokens_result = await db.execute(
        select(
            func.sum(CostLog.input_tokens),
            func.sum(CostLog.output_tokens),
        ).where(func.date(CostLog.timestamp) == today)
    )
    daily_tokens = daily_tokens_result.one()
    daily_input_tokens = daily_tokens[0] or 0
    daily_output_tokens = daily_tokens[1] or 0

    # Last cron run
    last_cron_result = await db.execute(
        select(CronLog).order_by(desc(CronLog.timestamp)).limit(1)
    )
    last_cron = last_cron_result.scalar_one_or_none()

    # Recent cron runs (last 7)
    recent_crons_result = await db.execute(
        select(CronLog).order_by(desc(CronLog.timestamp)).limit(7)
    )
    recent_crons = list(recent_crons_result.scalars().all())

    # Recent failures
    failures_result = await db.execute(
        select(Run)
        .where(Run.status == "failed")
        .order_by(desc(Run.run_timestamp))
        .limit(10)
    )
    recent_failures = list(failures_result.scalars().all())

    # Total runs today
    today_runs_result = await db.execute(
        select(func.count(Run.id)).where(
            and_(Run.run_date == today, Run.status == "complete")
        )
    )
    today_runs_count = today_runs_result.scalar() or 0

    return templates.TemplateResponse("status.html", {
        "request": request,
        "active_page": "status",
        "daily_cost": float(daily_cost),
        "monthly_cost": float(monthly_cost),
        "daily_cap": float(settings.daily_cost_cap_usd),
        "monthly_cap": float(settings.monthly_cost_cap_usd),
        "daily_input_tokens": daily_input_tokens,
        "daily_output_tokens": daily_output_tokens,
        "last_cron": last_cron,
        "recent_crons": recent_crons,
        "recent_failures": recent_failures,
        "today_runs_count": today_runs_count,
        "current_date": today.strftime("%A, %B %d, %Y"),
    })
