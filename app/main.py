"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import login, dashboard, portfolio, ticker, watchlist, history, run, status, about, intelligence

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


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    from app.database import engine
    await engine.dispose()
