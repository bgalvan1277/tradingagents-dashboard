"""Global News route: macro intelligence, news feeds, and geopolitical signals."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/global", response_class=HTMLResponse)
async def global_news_page(request: Request):
    """Global Intelligence dashboard with live news feeds and market sentiment."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    from app.services.global_intel import fetch_global_intel
    intel = await fetch_global_intel()

    return templates.TemplateResponse(request, "global_news.html", context={
        "active_page": "global",
        "intel": intel,
    })


@router.get("/api/global/refresh", response_class=HTMLResponse)
async def global_news_refresh(request: Request):
    """HTMX endpoint to refresh news feed data."""
    from app.auth import get_current_user
    if not get_current_user(request):
        return HTMLResponse("<p class='text-red-400'>Unauthorized</p>", status_code=401)

    from app.services.global_intel import fetch_global_intel, _cache
    # Clear cache to force refresh
    keys_to_clear = [k for k in _cache if k.startswith("news_feeds")]
    for k in keys_to_clear:
        del _cache[k]

    intel = await fetch_global_intel()

    # Return just the news feed cards (partial HTML for HTMX)
    return templates.TemplateResponse(request, "partials/global_news_feeds.html", context={
        "intel": intel,
    })
