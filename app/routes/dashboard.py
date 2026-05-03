"""Dashboard route: market overview with news and trends."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Show the market overview dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "dashboard.html")
