"""Public-facing website routes (no auth required)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request):
    """Public How It Works page."""
    return templates.TemplateResponse(request, "public/how.html")


@router.get("/about-us", response_class=HTMLResponse)
async def about_us(request: Request):
    """Public About Us page."""
    return templates.TemplateResponse(request, "public/about.html")


@router.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    """Public Contact page."""
    return templates.TemplateResponse(request, "public/contact.html")


@router.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    """Public FAQ page."""
    return templates.TemplateResponse(request, "public/faq.html")


@router.get("/wp-admin", response_class=HTMLResponse)
@router.get("/wp-admin/", response_class=HTMLResponse)
@router.get("/wp-login.php", response_class=HTMLResponse)
async def wp_honeypot(request: Request):
    """WordPress honeypot."""
    return FileResponse("app/static/wp-admin/index.html", media_type="text/html")
