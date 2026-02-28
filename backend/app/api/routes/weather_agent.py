"""Weather risk and shipment weather exposure API (from hackathon POC)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.weather import run_weather_agent
from app.config import settings
from app.schemas.weather_agent import (
    HealthResponse,
    ShipmentInput,
    ShipmentWeatherExposureResponse,
)

router = APIRouter(prefix="/api/v1", tags=["weather-agent"])


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="weather-agent",
        weather_api_configured=bool(settings.weather_api_key),
    )


@router.post(
    "/shipment/weather-exposure", response_model=ShipmentWeatherExposureResponse
)
async def get_weather_exposure(body: ShipmentInput):
    """
    Analyse weather exposure for a shipment from Supplier to OEM.
    Returns a day-by-day risk timeline and a structured payload for the Risk Analysis Agent.
    """
    try:
        result = await run_weather_agent(
            supplier_city=body.supplier_city.strip(),
            oem_city=body.oem_city.strip(),
            shipment_start_date=body.shipment_start_date.strip(),
            transit_days=body.transit_days,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Shipment weather agent failed: {e}"
        )
