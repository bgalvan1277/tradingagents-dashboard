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
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/screener.html")


@router.get("/earnings", response_class=HTMLResponse)
async def earnings(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/earnings.html")


@router.get("/sectors", response_class=HTMLResponse)
async def sectors(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/sectors.html")


@router.get("/economic", response_class=HTMLResponse)
async def economic(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/economic.html")


@router.get("/congress", response_class=HTMLResponse)
async def congress(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/congress.html")


@router.get("/contracts", response_class=HTMLResponse)
async def contracts(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/contracts.html")


@router.get("/edgar", response_class=HTMLResponse)
async def edgar(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/edgar.html")


@router.get("/fred", response_class=HTMLResponse)
async def fred(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/fred.html")


@router.get("/darkpool", response_class=HTMLResponse)
async def darkpool(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Dark Pool Volume",
        "feed_desc": "Off-exchange trading activity from FINRA ATS data. Track institutional block trades, dark pool short volume ratios, and venue-level execution patterns that signal hidden accumulation or distribution before it surfaces in lit markets.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/>',
    })


@router.get("/shortinterest", response_class=HTMLResponse)
async def shortinterest(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Short Interest",
        "feed_desc": "Bi-monthly FINRA short interest reports by ticker. Monitor days-to-cover ratios, short interest as a percentage of float, and changes in short positioning to identify potential squeeze candidates and bearish conviction levels.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/>',
    })


@router.get("/fda", response_class=HTMLResponse)
async def fda(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/fda.html")


@router.get("/reddit", response_class=HTMLResponse)
async def reddit(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Reddit Sentiment",
        "feed_desc": "WallStreetBets and r/investing mention velocity tracking, sentiment classification, and momentum scoring. Surface tickers gaining retail conviction before institutional recognition, and detect coordinated positioning events in real-time.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z"/>',
    })


@router.get("/lobbying", response_class=HTMLResponse)
async def lobbying(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Lobbying Spend",
        "feed_desc": "Corporate lobbying expenditure data from OpenSecrets.org. Track which companies are investing in regulatory influence, identify sectors facing legislative headwinds, and detect policy risk before it materializes in earnings guidance.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>',
    })


@router.get("/insider", response_class=HTMLResponse)
async def insider(request: Request):
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
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "intelligence/coming_soon.html", context={
        "feed_title": "Options Flow",
        "feed_desc": "Unusual options activity detection, large block trade alerts, and smart money positioning signals. Surface high-conviction directional bets from institutional participants before they reflect in the underlying equity price.",
        "feed_icon": '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/>',
    })
