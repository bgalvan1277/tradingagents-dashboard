"""SimTrader paper trading routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services import simtrader

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/simtrader", response_class=HTMLResponse)
async def simtrader_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Main SimTrader dashboard."""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    account = await simtrader.get_account(db)
    positions = await simtrader.get_positions(db, with_prices=True)
    portfolio = await simtrader.get_portfolio_value(db)
    history = await simtrader.get_trade_history(db, limit=30)
    performance = await simtrader.get_performance(db)

    return templates.TemplateResponse(request, "simtrader.html", context={
        "account": account,
        "positions": positions,
        "portfolio": portfolio,
        "history": history,
        "performance": performance,
        "active_page": "simtrader",
    })


@router.post("/simtrader/trade", response_class=HTMLResponse)
async def execute_trade(
    request: Request,
    ticker: str = Form(...),
    side: str = Form(...),
    shares: int = Form(...),
    run_id: Optional[int] = Form(None),
    note: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Execute a simulated trade."""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    result = await simtrader.execute_trade(
        db, ticker_symbol=ticker, side=side, shares=shares,
        run_id=run_id if run_id else None, note=note if note else None,
    )

    if result.get("error"):
        # Re-render page with error
        account = await simtrader.get_account(db)
        positions = await simtrader.get_positions(db, with_prices=True)
        portfolio = await simtrader.get_portfolio_value(db)
        history = await simtrader.get_trade_history(db, limit=30)
        performance = await simtrader.get_performance(db)
        return templates.TemplateResponse(request, "simtrader.html", context={
            "account": account,
            "positions": positions,
            "portfolio": portfolio,
            "history": history,
            "performance": performance,
            "active_page": "simtrader",
            "trade_error": result["error"],
        })

    return RedirectResponse(url="/simtrader", status_code=303)


@router.post("/simtrader/close/{ticker}")
async def close_position(request: Request, ticker: str, db: AsyncSession = Depends(get_db)):
    """Close an entire position at market price."""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    from sqlalchemy import text
    pos = (await db.execute(
        text("SELECT shares FROM sim_positions WHERE ticker_symbol = :s"),
        {"s": ticker.upper()}
    )).mappings().first()

    if pos and pos["shares"] > 0:
        await simtrader.execute_trade(db, ticker, "sell", pos["shares"])

    return RedirectResponse(url="/simtrader", status_code=303)


@router.post("/simtrader/reset")
async def reset_account(request: Request, db: AsyncSession = Depends(get_db)):
    """Reset the SimTrader account to starting capital."""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    await simtrader.reset_account(db)
    return RedirectResponse(url="/simtrader", status_code=303)


@router.get("/api/simtrader/price/{ticker}")
async def get_price(request: Request, ticker: str):
    """Return live price for a ticker symbol."""
    if not get_current_user(request):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    price = await simtrader.get_live_price(ticker.upper())
    if price is None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": f"Could not fetch price for {ticker.upper()}"}, status_code=404)

    from fastapi.responses import JSONResponse
    return JSONResponse({"ticker": ticker.upper(), "price": float(price)})
