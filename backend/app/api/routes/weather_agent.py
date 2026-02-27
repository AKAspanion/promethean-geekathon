"""Weather risk and shipment weather exposure API (from hackathon POC)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.legacy_weather import run_weather_risk_agent
from app.agents.shipment_weather import run_shipment_weather_agent
from app.config import settings
from app.schemas.weather_agent import (
    HealthResponse,
    LocationInfo,
    RiskSummary,
    ShipmentInput,
    ShipmentWeatherExposureResponse,
    WeatherCondition,
    WeatherRiskResponse,
)

router = APIRouter(prefix="/api/v1", tags=["weather-agent"])


def _normalize_current(data: dict) -> tuple[LocationInfo, WeatherCondition]:
    loc = data.get("location") or {}
    current = data.get("current") or {}
    cond = current.get("condition") or {}

    location = LocationInfo(
        name=loc.get("name", ""),
        region=loc.get("region"),
        country=loc.get("country", ""),
        lat=float(loc.get("lat", 0)),
        lon=float(loc.get("lon", 0)),
        tz_id=loc.get("tz_id"),
        localtime=loc.get("localtime"),
    )
    weather = WeatherCondition(
        text=cond.get("text", "Unknown"),
        temp_c=float(current.get("temp_c", 0)),
        feelslike_c=float(current.get("feelslike_c", current.get("temp_c", 0))),
        wind_kph=float(current.get("wind_kph", 0)),
        wind_degree=current.get("wind_degree"),
        pressure_mb=float(current.get("pressure_mb", 1013)),
        precip_mm=float(current.get("precip_mm", 0)),
        humidity=int(current.get("humidity", 0)),
        cloud=int(current.get("cloud", 0)),
        vis_km=float(current.get("vis_km", 10)),
        uv=current.get("uv"),
        gust_kph=current.get("gust_kph"),
        condition_code=cond.get("code"),
    )
    return location, weather


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="weather-agent",
        weather_api_configured=bool(settings.weather_api_key),
    )


@router.get("/weather/risk", response_model=WeatherRiskResponse)
async def get_weather_risk(city: str):
    city = city.strip()

    state = await run_weather_risk_agent(city)
    data = state.get("weather_data")
    if not data:
        raise HTTPException(
            status_code=502,
            detail="Weather service unavailable or invalid location. Check WEATHER_API_KEY and try city (e.g. New Delhi, London).",
        )

    location, weather = _normalize_current(data)
    risk_dict = state.get("risk_dict") or {}
    if "overall_level" in risk_dict and hasattr(risk_dict["overall_level"], "value"):
        risk_dict = {**risk_dict, "overall_level": risk_dict["overall_level"].value}
    risk = RiskSummary(**risk_dict)
    agent_summary = state.get("llm_summary")

    return WeatherRiskResponse(
        location=location,
        weather=weather,
        risk=risk,
        agent_summary=agent_summary,
        raw_weather=data.get("current") if data else None,
    )


@router.post(
    "/shipment/weather-exposure", response_model=ShipmentWeatherExposureResponse
)
async def get_shipment_weather_exposure(body: ShipmentInput):
    """
    Analyse weather exposure for a shipment from Supplier to OEM.
    Returns a day-by-day risk timeline and a structured payload for the Risk Analysis Agent.
    """
    try:
        result = await run_shipment_weather_agent(
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
