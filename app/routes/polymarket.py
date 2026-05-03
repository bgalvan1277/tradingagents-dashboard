"""Polymarket routes: prediction market analysis pages."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/poly/analysis", response_class=HTMLResponse)
async def poly_analysis(request: Request):
    """Polymarket analysis dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "poly_analysis.html")


@router.get("/poly/intelligence", response_class=HTMLResponse)
async def poly_intelligence(request: Request):
    """Polymarket intelligence feeds."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "poly_intelligence.html")


@router.get("/poly/news", response_class=HTMLResponse)
async def poly_news(request: Request):
    """Polymarket news feed."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "poly_news.html")


@router.get("/poly/agents", response_class=HTMLResponse)
async def poly_agents(request: Request):
    """Polymarket agent team profiles."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(request, "poly_agents.html")
