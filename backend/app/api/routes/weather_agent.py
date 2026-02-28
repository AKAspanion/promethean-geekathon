"""Weather risk and shipment weather exposure API (from hackathon POC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.weather import run_weather_graph
from app.api.deps import get_current_oem
from app.config import settings
from app.database import get_db
from app.models.oem import Oem
from app.schemas.weather_agent import HealthResponse
from app.services.agent_types import OemScope

router = APIRouter(prefix="/api/v1", tags=["weather-agent"])


class WeatherExposureRequest(BaseModel):
    supplier_id: str


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="weather-agent",
        weather_api_configured=bool(settings.weather_api_key),
    )


@router.post("/shipment/weather-exposure")
async def get_weather_exposure(
    body: WeatherExposureRequest,
    oem: Oem = Depends(get_current_oem),
):
    """
    Analyse weather exposure for a shipment from Supplier to OEM.

    Supplier city is resolved from the database using the ``supplier_id``
    in the request body.  OEM city is resolved from the authenticated user.
    Transit duration and start date default to today inside the graph.

    Returns ``{"risks": [...], "opportunities": [...]}`` ready for the
    Risk Analysis Agent.
    """
    scope: OemScope = {
        "oemId": str(oem.id),
        "oemName": oem.name or "",
        "supplierNames": [],
        "locations": [],
        "cities": [],
        "countries": [],
        "regions": [],
        "commodities": [],
        "supplierId": body.supplier_id,
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
