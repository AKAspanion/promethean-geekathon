"""Pydantic schemas for the weather/shipment exposure agent API (from hackathon POC)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class LocationQuery(BaseModel):
    city: str = Field(..., min_length=1, max_length=100)


class ShipmentInput(BaseModel):
    supplier_city: str = Field(
        ..., min_length=1, max_length=100, description="Origin city (Supplier)"
    )
    oem_city: str = Field(
        ..., min_length=1, max_length=100, description="Destination city (OEM)"
    )
    shipment_start_date: str = Field(
        ..., description="Shipment start date in YYYY-MM-DD format"
    )
    transit_days: int = Field(
        ..., ge=1, le=30, description="Estimated transit duration in days"
    )


class RiskFactor(BaseModel):
    factor: str
    level: RiskLevel
    score: float = Field(..., ge=0, le=100)
    summary: str
    details: str | None = None
    mitigation: str | None = None


class RiskSummary(BaseModel):
    overall_level: RiskLevel
    overall_score: float = Field(..., ge=0, le=100)
    factors: list[RiskFactor] = Field(default_factory=list)
    primary_concerns: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class WeatherCondition(BaseModel):
    text: str
    temp_c: float
    feelslike_c: float
    wind_kph: float
    wind_degree: int | None
    pressure_mb: float
    precip_mm: float
    humidity: int
    cloud: int
    vis_km: float
    uv: float | None
    gust_kph: float | None = None
    condition_code: int | None = None


class LocationInfo(BaseModel):
    name: str
    region: str | None
    country: str
    lat: float
    lon: float
    tz_id: str | None
    localtime: str | None


class WeatherRiskResponse(BaseModel):
    location: LocationInfo
    weather: WeatherCondition
    risk: RiskSummary
    agent_summary: str | None = None
    raw_weather: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "weather-agent"
    weather_api_configured: bool = False


class DayWeatherSnapshot(BaseModel):
    date: str
    day_number: int
    location_name: str
    estimated_location: str
    condition: str
    temp_c: float
    min_temp_c: float | None = None
    max_temp_c: float | None = None
    wind_kph: float
    precip_mm: float
    vis_km: float
    humidity: int
    is_historical: bool


class DayRiskSnapshot(BaseModel):
    date: str
    day_number: int
    location_name: str
    weather: DayWeatherSnapshot
    risk: RiskSummary
    risk_summary_text: str


class ShipmentWeatherExposureResponse(BaseModel):
    supplier_city: str
    oem_city: str
    shipment_start_date: str
    transit_days: int
    days: list[DayRiskSnapshot]
    overall_exposure_level: RiskLevel
    overall_exposure_score: float
    risk_analysis_payload: dict[str, Any]
    agent_summary: str | None = None
