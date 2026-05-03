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
@router.get("/wp-admin.php", response_class=HTMLResponse)
@router.get("/wp-login.php", response_class=HTMLResponse)
@router.get("/wp-login", response_class=HTMLResponse)
@router.get("/wordpress/wp-login.php", response_class=HTMLResponse)
@router.get("/wordpress/wp-admin", response_class=HTMLResponse)
@router.get("/wp/wp-login.php", response_class=HTMLResponse)
@router.get("/wp/wp-admin", response_class=HTMLResponse)
@router.get("/wp-admin/install.php", response_class=HTMLResponse)
@router.get("/wp-admin/setup-config.php", response_class=HTMLResponse)
@router.get("/wp-admin/upgrade.php", response_class=HTMLResponse)
@router.get("/xmlrpc.php", response_class=HTMLResponse)
@router.get("/wp-config.php", response_class=HTMLResponse)
@router.get("/wp-cron.php", response_class=HTMLResponse)
@router.get("/wp-settings.php", response_class=HTMLResponse)
@router.get("/wp-includes/", response_class=HTMLResponse)
@router.get("/wp-content/", response_class=HTMLResponse)
@router.post("/wp-login.php", response_class=HTMLResponse)
@router.post("/wp-admin", response_class=HTMLResponse)
@router.post("/xmlrpc.php", response_class=HTMLResponse)
async def wp_honeypot(request: Request):
    """WordPress honeypot — catches all common WP probe paths."""
    return FileResponse("app/static/wp-admin/index.html", media_type="text/html")
