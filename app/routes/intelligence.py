"""Intelligence Gathering routes: data feeds and market intelligence."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth

router = APIRouter(prefix="/intelligence")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def intelligence_hub(request: Request):
    """Intelligence Gathering landing page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/hub.html")


@router.get("/screener", response_class=HTMLResponse)
async def screener(request: Request):
    """Market Screener page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/screener.html")


@router.get("/earnings", response_class=HTMLResponse)
async def earnings(request: Request):
    """Earnings Calendar page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/earnings.html")


@router.get("/sectors", response_class=HTMLResponse)
async def sectors(request: Request):
    """Sector Rotation page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/sectors.html")


@router.get("/economic", response_class=HTMLResponse)
async def economic(request: Request):
    """Economic Data page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/economic.html")


@router.get("/insider", response_class=HTMLResponse)
async def insider(request: Request):
    """Insider Activity page (coming soon)."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Insider Activity",
        "feed_desc": "SEC Form 4 filings, insider buy/sell signals, and executive transaction monitoring. This feed will track material insider trades across your watchlist and flag unusual accumulation or distribution patterns.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>',
    })


@router.get("/options", response_class=HTMLResponse)
async def options(request: Request):
    """Options Flow page (coming soon)."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Options Flow",
        "feed_desc": "Unusual options activity detection, large block trade alerts, and smart money positioning signals. This feed will surface high-conviction directional bets from institutional participants before they reflect in the underlying equity price.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/>',
    })
