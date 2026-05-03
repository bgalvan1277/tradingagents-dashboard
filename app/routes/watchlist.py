"""Watchlist management routes."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.database import get_db
from app.models import Ticker, WatchlistEntry

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Show watchlist management page."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Get all tickers with their watchlist info
    query = (
        select(Ticker, WatchlistEntry)
        .outerjoin(WatchlistEntry, WatchlistEntry.ticker_id == Ticker.id)
        .order_by(WatchlistEntry.group_name, WatchlistEntry.position, Ticker.symbol)
    )
    result = await db.execute(query)
    items = result.all()

    # Group by category
    groups = {}
    for ticker, wl in items:
        group = wl.group_name if wl else (ticker.category or "default")
        if group not in groups:
            groups[group] = []
        groups[group].append({"ticker": ticker, "watchlist": wl})

    return templates.TemplateResponse(request, "watchlist.html", context={
        "active_page": "watchlist",
        "groups": groups,
        "total_tickers": len(items),
    })


@router.post("/watchlist/add", response_class=HTMLResponse)
async def add_ticker(
    request: Request,
    symbol: str = Form(...),
    name: str = Form(""),
    category: str = Form("watching"),
    group_name: str = Form("default"),
    model_tier: str = Form("pro"),
    redirect: str = Form("/watchlist"),
    db: AsyncSession = Depends(get_db),
):
    """Add a new ticker to the watchlist."""
    redirect_auth = require_auth(request)
    if redirect_auth:
        return redirect_auth

    symbol = symbol.upper().strip()

    # Check if ticker already exists
    existing = await db.execute(
        select(Ticker).where(Ticker.symbol == symbol)
    )
    ticker = existing.scalar_one_or_none()

    if ticker:
        # Reactivate if inactive
        ticker.active = True
        ticker.category = category
        ticker.model_tier = model_tier
        if name:
            ticker.name = name
    else:
        # Create new ticker
        ticker = Ticker(
            symbol=symbol,
            name=name or None,
            category=category,
            active=True,
            model_tier=model_tier,
        )
        db.add(ticker)
        await db.flush()

    # Ensure watchlist entry exists
    wl_check = await db.execute(
        select(WatchlistEntry).where(WatchlistEntry.ticker_id == ticker.id)
    )
    if not wl_check.scalar_one_or_none():
        # Get max position for ordering
        max_pos = await db.execute(
            select(func.max(WatchlistEntry.position))
            .where(WatchlistEntry.group_name == group_name)
        )
        next_pos = (max_pos.scalar() or 0) + 1

        wl_entry = WatchlistEntry(
            ticker_id=ticker.id,
            group_name=group_name,
            position=next_pos,
            frequency="daily",
        )
        db.add(wl_entry)

    await db.commit()
    # Sanitize redirect to prevent open redirect
    safe_redirect = redirect if redirect.startswith("/") else "/watchlist"
    return RedirectResponse(url=safe_redirect, status_code=303)


@router.post("/watchlist/remove/{symbol}")
async def remove_ticker(
    request: Request,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a ticker from the watchlist (deactivate, don't delete data)."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    symbol = symbol.upper()
    result = await db.execute(select(Ticker).where(Ticker.symbol == symbol))
    ticker = result.scalar_one_or_none()

    if ticker:
        ticker.active = False
        # Remove watchlist entry
        await db.execute(
            delete(WatchlistEntry).where(WatchlistEntry.ticker_id == ticker.id)
        )
        await db.commit()

    return RedirectResponse(url="/watchlist", status_code=303)


@router.get("/api/ticker/{symbol}/rename")
async def rename_ticker(
    request: Request,
    symbol: str,
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Rename a ticker (must be logged in). Usage: /api/ticker/CRWV/rename?name=CoreWeave"""
    from fastapi.responses import JSONResponse
    from app.auth import get_current_user

    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await db.execute(select(Ticker).where(Ticker.symbol == symbol.upper()))
    ticker = result.scalar_one_or_none()
    if not ticker:
        return JSONResponse({"error": f"Ticker {symbol} not found"}, status_code=404)

    old_name = ticker.name
    ticker.name = name
    await db.commit()
    return JSONResponse({"symbol": symbol.upper(), "old_name": old_name, "new_name": name})
