"""Mock tracking by AWB code; proxy to external mock server by supplier_id."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.mock_tracking import get_tracking

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping/tracking", tags=["shipping"])

MOCK_TRACKING_COLLECTION = "shipment-tracking"


@router.get("/by-supplier/{supplier_id}")
async def get_tracking_by_supplier(supplier_id: str) -> dict:
    """
    Proxy shipment-tracking request to the configured mock server.
    Returns the same shape as the mock server: { "items": [...] }.
    Used by the frontend so it does not call the mock server directly.
    """
    base_url = settings.mock_server_base_url
    if not base_url or not supplier_id.strip():
        logger.debug(
            "mock_server_base_url not set or supplier_id empty — returning empty items"
        )
        return {"items": []}

    url = (
        f"{base_url.rstrip('/')}/{MOCK_TRACKING_COLLECTION}"
        f"?q=supplier_id:{supplier_id.strip()}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Mock server proxy HTTP error supplier_id=%s: %s", supplier_id, e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Mock server error: {e.response.text}",
        )
    except Exception as e:
        logger.warning("Mock server proxy error supplier_id=%s: %s", supplier_id, e)
        raise HTTPException(
            status_code=503,
            detail="Tracking service temporarily unavailable",
        )


@router.get("/{awb_code}")
async def get_tracking_by_awb(awb_code: str) -> dict:
    payload = get_tracking(awb_code)
    if payload is None:
        raise HTTPException(
            status_code=404, detail="Tracking not found for this AWB code"
        )
    return payload
