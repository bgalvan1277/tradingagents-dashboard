"""Polymarket API proxy routes to avoid CORS issues."""

import httpx
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from app.auth import require_auth

router = APIRouter(prefix="/api/polymarket", tags=["polymarket"])

GAMMA_BASE = "https://gamma-api.polymarket.com"


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
