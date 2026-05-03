"""Dashboard route: market overview with news and trends."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Show the market overview dashboard for authenticated users,
    or the public landing page for visitors."""
    if not get_current_user(request):
        return templates.TemplateResponse(request, "public/home.html")

    return templates.TemplateResponse(request, "dashboard.html")
