"""Run a single ticker analysis on demand.

Usage:
    python scripts/run_single.py PLTR
    python scripts/run_single.py NVDA 2025-05-02
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
from app.models import Run
from app.services.runner import run_analysis_sync, save_run_results, mark_run_failed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_single")


async def run_single(ticker_symbol: str, trade_date: str = None):
    """Run analysis for a single ticker and save results."""
    today = date.today()
    if not trade_date:
        trade_date = today.strftime("%Y-%m-%d")

    logger.info("Starting analysis for %s (trade date: %s)", ticker_symbol, trade_date)
    start_time = time.time()

    async with async_session() as db:
        # Create run record
        run = Run(
            ticker_symbol=ticker_symbol,
            run_date=today,
            status="running",
            model_used="deepseek-chat",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        try:
            # Run the TradingAgents analysis (this takes 2-5 minutes)
            logger.info("Calling TradingAgents for %s... (this takes a few minutes)", ticker_symbol)
            state, decision, usage = run_analysis_sync(ticker_symbol, trade_date)

            await save_run_results(db, run, state, decision, usage=usage)

            elapsed = round(time.time() - start_time, 1)
            logger.info("Analysis complete for %s in %.1fs", ticker_symbol, elapsed)
            logger.info("Decision: %s", decision)
            if usage.get("total_tokens"):
                logger.info(
                    "Tokens: %d in / %d out / $%.6f",
                    usage["input_tokens"], usage["output_tokens"],
                    float(usage.get("cost_usd", 0)),
                )

        except Exception as e:
            error_msg = str(e)
            logger.error("Analysis failed for %s: %s", ticker_symbol, error_msg)
            await mark_run_failed(db, run, error_msg)
            raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_single.py TICKER [YYYY-MM-DD]")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    trade_dt = sys.argv[2] if len(sys.argv) > 2 else None

    asyncio.run(run_single(ticker, trade_dt))
