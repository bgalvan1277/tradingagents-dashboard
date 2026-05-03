"""Daily cron script: runs TradingAgents analysis for all watchlist tickers.

Called by system cron on weekdays:
    0 7 * * 1-5 cd /path/to/project && /path/to/venv/bin/python scripts/daily_cron.py
"""

import asyncio
import logging
import sys
import os
import time
from datetime import date, datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env into actual environment variables (needed by TradingAgents/LangChain)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import select
from app.database import async_session
from app.models import Ticker, WatchlistEntry, Run, CronLog
from app.services.runner import run_analysis_sync, save_run_results, mark_run_failed
from app.services.cost import check_cost_cap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("daily_cron")


async def run_daily():
    """Run analysis for all daily watchlist tickers."""
    start_time = time.time()
    today = date.today()

    # Skip weekends
    if today.weekday() >= 5:
        logger.info("Weekend detected, skipping daily run.")
        return

    logger.info("Starting daily analysis run for %s", today)

    async with async_session() as db:
        # Check cost cap before starting
        allowed, reason = await check_cost_cap(db)
        if not allowed:
            logger.warning("Cost cap exceeded, aborting: %s", reason)
            cron_log = CronLog(
                status="failed",
                tickers_attempted=0,
                tickers_succeeded=0,
                tickers_failed=0,
                total_cost_usd=Decimal("0"),
                error_details={"reason": reason},
                duration_seconds=Decimal("0"),
            )
            db.add(cron_log)
            await db.commit()
            return

        # Get all daily tickers
        query = (
            select(Ticker)
            .join(WatchlistEntry, WatchlistEntry.ticker_id == Ticker.id)
            .where(Ticker.active == True, WatchlistEntry.frequency == "daily")
            .order_by(WatchlistEntry.position)
        )
        result = await db.execute(query)
        tickers = list(result.scalars().all())

        if not tickers:
            logger.info("No daily tickers configured.")
            return

        logger.info("Processing %d tickers: %s",
                     len(tickers), ", ".join(t.symbol for t in tickers))

        succeeded = 0
        failed = 0
        total_cost = Decimal("0")
        errors = {}

        for ticker in tickers:
            # Re-check cost cap before each ticker
            allowed, reason = await check_cost_cap(db)
            if not allowed:
                logger.warning("Cost cap hit during batch, stopping: %s", reason)
                errors[ticker.symbol] = reason
                failed += 1
                continue

            # Create run record
            run = Run(
                ticker_symbol=ticker.symbol,
                run_date=today,
                status="running",
                model_used=ticker.model_tier,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            logger.info("Running analysis for %s...", ticker.symbol)

            try:
                # Run analysis (this is the slow part, 2-5 minutes per ticker)
                trade_date_str = today.strftime("%Y-%m-%d")
                state, decision, usage = run_analysis_sync(ticker.symbol, trade_date_str)

                await save_run_results(db, run, state, decision, usage=usage)
                total_cost += usage.get("cost_usd", Decimal("0"))
                succeeded += 1
                logger.info("Completed %s: %s", ticker.symbol, decision)

            except Exception as e:
                error_msg = str(e)
                logger.error("Failed %s: %s", ticker.symbol, error_msg)
                await mark_run_failed(db, run, error_msg)
                errors[ticker.symbol] = error_msg
                failed += 1
                # Continue to next ticker, don't kill the batch

        # Log cron execution
        duration = Decimal(str(round(time.time() - start_time, 2)))
        cron_status = "success" if failed == 0 else ("partial" if succeeded > 0 else "failed")

        cron_log = CronLog(
            status=cron_status,
            tickers_attempted=len(tickers),
            tickers_succeeded=succeeded,
            tickers_failed=failed,
            total_cost_usd=total_cost,
            error_details=errors if errors else None,
            duration_seconds=duration,
        )
        db.add(cron_log)
        await db.commit()

        logger.info(
            "Daily run complete: %d/%d succeeded, %d failed, %.2fs elapsed",
            succeeded, len(tickers), failed, float(duration),
        )


if __name__ == "__main__":
    asyncio.run(run_daily())
