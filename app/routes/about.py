"""About route: team profiles page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """Show the About / Meet the Team page."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "about.html")


@router.get("/the-process", response_class=HTMLResponse)
async def the_process(request: Request):
    """Show The Process walkthrough page."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "the_process.html")
