"""Polymarket API proxy routes and analysis endpoints."""

import json
import logging
import threading
import uuid

import httpx
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from app.auth import require_auth, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/polymarket", tags=["polymarket"])

GAMMA_BASE = "https://gamma-api.polymarket.com"

# In-memory store for poly analysis results (lightweight, no DB needed yet)
_poly_analyses: dict = {}


@router.get("/markets")
async def proxy_markets(
    request: Request,
    limit: int = Query(10),
    active: bool = Query(True),
    closed: bool = Query(False),
    order: str = Query("volume"),
    ascending: bool = Query(False),
):
    """Proxy Polymarket Gamma API to avoid CORS."""
    redirect = require_auth(request)
    if redirect:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "order": order,
        "ascending": str(ascending).lower(),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_BASE}/markets", params=params)
            resp.raise_for_status()
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@router.post("/analyze")
async def submit_analysis(request: Request):
    """Submit a Polymarket question for AI analysis."""
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    question = body.get("question", "")
    yes_price = float(body.get("yes_price", 50))
    no_price = float(body.get("no_price", 50))
    volume = body.get("volume", "")
    end_date = body.get("end_date", "")
    market_slug = body.get("slug", "")

    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)

    analysis_id = str(uuid.uuid4())[:8]
    _poly_analyses[analysis_id] = {"status": "running", "question": question}

    # Run in background thread
    t = threading.Thread(
        target=_run_poly_analysis_thread,
        args=(analysis_id, question, yes_price, no_price, volume, end_date, market_slug),
        daemon=True,
    )
    t.start()

    return JSONResponse({"analysis_id": analysis_id, "status": "running"})


@router.get("/analyze/{analysis_id}")
async def get_analysis(request: Request, analysis_id: str):
    """Check status / get results of a poly analysis."""
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = _poly_analyses.get(analysis_id)
    if not result:
        return JSONResponse({"error": "Analysis not found"}, status_code=404)

    return JSONResponse(result)


def _run_poly_analysis_thread(analysis_id: str, question: str,
                               yes_price: float, no_price: float,
                               volume: str, end_date: str, market_slug: str):
    """Background thread for poly analysis."""
    try:
        from app.services.poly_runner import run_poly_analysis_sync

        logger.info("[poly] Starting analysis: %s", question[:80])
        result = run_poly_analysis_sync(
            question=question,
            yes_price=yes_price,
            no_price=no_price,
            volume=volume,
            end_date=end_date,
            market_slug=market_slug,
        )
        result["question"] = question
        result["market_yes"] = yes_price
        result["market_no"] = no_price
        _poly_analyses[analysis_id] = result
        logger.info("[poly] Analysis complete: %s → %s (edge: %s)",
                    question[:60], result.get("recommendation"), result.get("edge"))

    except Exception as e:
        logger.error("[poly] Analysis failed: %s", e)
        _poly_analyses[analysis_id] = {
            "status": "failed",
            "error": str(e),
            "question": question,
        }
