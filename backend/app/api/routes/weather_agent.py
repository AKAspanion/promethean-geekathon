"""Weather risk and shipment weather exposure API (from hackathon POC)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.weather import run_weather_graph
from app.config import settings
from app.schemas.weather_agent import HealthResponse
from app.services.agent_types import OemScope

router = APIRouter(prefix="/api/v1", tags=["weather-agent"])

# Hardcoded IDs until the API accepts them as request parameters.
_OEM_ID = "9c682575-0285-437f-a1e5-fdba3128fbf5"
_SUPPLIER_ID = "5d935889-7558-4e72-ba73-a772dd30f666"


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="weather-agent",
        weather_api_configured=bool(settings.weather_api_key),
    )


@router.post("/shipment/weather-exposure")
async def get_weather_exposure():
    """
    Analyse weather exposure for a shipment from Supplier to OEM.

    Supplier and OEM cities are resolved from the database using the
    hardcoded entity IDs.  Transit duration and start date default to
    today inside the graph.

    Returns ``{"risks": [...], "opportunities": [...]}`` ready for the
    Risk Analysis Agent.
    """
    scope: OemScope = {
        "oemId": _OEM_ID,
        "oemName": "",
        "supplierNames": [],
        "locations": [],
        "cities": [],
        "countries": [],
        "regions": [],
        "commodities": [],
        "supplierId": _SUPPLIER_ID,
        "supplierName": "",
    }

    try:
        return await run_weather_graph(scope)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Shipment weather agent failed: {e}"
        )
