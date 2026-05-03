"""FastAPI application entry point."""

import os
from dotenv import load_dotenv

# Load .env into os.environ so TradingAgents/LangChain can find API keys
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import login, dashboard, portfolio, ticker, watchlist, history, run, status, about, intelligence, public, simtrader, briefing

app = FastAPI(
    title="TradingAgents Dashboard",
    description="Personal multi-agent stock analysis dashboard",
    docs_url=None,   # No public API docs needed
    redoc_url=None,
)

# Mount all route modules
app.include_router(login.router)
app.include_router(dashboard.router)
app.include_router(portfolio.router)
app.include_router(ticker.router)
app.include_router(watchlist.router)
app.include_router(history.router)
app.include_router(run.router)
app.include_router(status.router)
app.include_router(about.router)
app.include_router(intelligence.router)
app.include_router(public.router)
app.include_router(simtrader.router)
app.include_router(briefing.router)

# Serve static files (avatars, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
async def startup():
    """Run on application startup."""
    # Auto-add new columns if they don't exist yet
    from app.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE run_details ADD COLUMN intelligence_briefing TEXT NULL"
            ))
        except Exception:
            pass  # Column already exists

        # SimTrader tables
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sim_account (
                id INT AUTO_INCREMENT PRIMARY KEY,
                starting_cash DECIMAL(14,2) DEFAULT 100000.00,
                cash_balance DECIMAL(14,2) DEFAULT 100000.00,
                inception_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sim_trades (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker_symbol VARCHAR(10) NOT NULL,
                side VARCHAR(4) NOT NULL,
                shares INT NOT NULL,
                price DECIMAL(12,4) NOT NULL,
                total_value DECIMAL(14,2) NOT NULL,
                realized_pnl DECIMAL(14,2) NULL,
                run_id INT NULL,
                note VARCHAR(255) NULL,
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_sim_trades_ticker (ticker_symbol),
                INDEX idx_sim_trades_executed (executed_at),
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sim_positions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker_symbol VARCHAR(10) NOT NULL UNIQUE,
                shares INT NOT NULL DEFAULT 0,
                avg_cost DECIMAL(12,4) NOT NULL,
                total_cost_basis DECIMAL(14,2) NOT NULL,
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_sim_positions_ticker (ticker_symbol)
            )
        """))

        # Seed account if empty
        result = await conn.execute(text("SELECT COUNT(*) FROM sim_account"))
        count = result.scalar()
        if count == 0:
            await conn.execute(text(
                "INSERT INTO sim_account (starting_cash, cash_balance) VALUES (100000.00, 100000.00)"
            ))


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    from app.database import engine
    await engine.dispose()
