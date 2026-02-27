"""Mock tracking by AWB code."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.mock_tracking import get_tracking

router = APIRouter(prefix="/shipping/tracking", tags=["shipping"])


@router.get("/{awb_code}")
async def get_tracking_by_awb(awb_code: str) -> dict:
    payload = get_tracking(awb_code)
    if payload is None:
        raise HTTPException(
            status_code=404, detail="Tracking not found for this AWB code"
        )
    return payload
