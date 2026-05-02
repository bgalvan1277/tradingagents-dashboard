"""Cost tracking and cap enforcement."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CostLog


async def get_daily_cost(db: AsyncSession) -> Decimal:
    """Get total cost for today."""
    result = await db.execute(
        select(func.sum(CostLog.cost_usd)).where(
            func.date(CostLog.timestamp) == date.today()
        )
    )
    return result.scalar() or Decimal("0")


async def get_monthly_cost(db: AsyncSession) -> Decimal:
    """Get total cost for this month."""
    month_start = date.today().replace(day=1)
    result = await db.execute(
        select(func.sum(CostLog.cost_usd)).where(
            CostLog.timestamp >= datetime.combine(month_start, datetime.min.time())
        )
    )
    return result.scalar() or Decimal("0")


async def check_cost_cap(db: AsyncSession) -> tuple[bool, str]:
    """Check if we're within cost caps. Returns (allowed, reason)."""
    daily = await get_daily_cost(db)
    if daily >= settings.daily_cost_cap_usd:
        return False, f"Daily cap of ${settings.daily_cost_cap_usd} reached (${daily:.4f} spent)"

    monthly = await get_monthly_cost(db)
    if monthly >= settings.monthly_cost_cap_usd:
        return False, f"Monthly cap of ${settings.monthly_cost_cap_usd} reached (${monthly:.4f} spent)"

    return True, ""


async def log_cost(
    db: AsyncSession,
    run_id: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal,
) -> None:
    """Log a cost entry."""
    entry = CostLog(
        run_id=run_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
    db.add(entry)
    await db.commit()
