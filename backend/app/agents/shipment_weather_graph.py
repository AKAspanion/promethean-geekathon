"""
Shipment Weather Exposure Graph Agent
=====================================
A LangGraph StateGraph that drives day-by-day weather exposure analysis
for a shipment route between a supplier city and an OEM city.

Graph structure
---------------

    START
      |
      v
  [resolve_cities]       <- extract supplier/OEM cities from scope (DB lookup)
      |
      v
  [fetch_forecasts]      <- parallel forecast fetch for supplier + OEM cities
      |
      v
  [build_daily_timeline] <- day-by-day weather + risk via compute_risk()
      |
      v
  [build_exposure_risks] <- convert exposure payload into risk/opportunity dicts
      |
      v
  [llm_summary]          <- optional LLM executive summary (fallback: rule-based)
      |
      v
     END

Public entrypoint: ``run_shipment_weather_graph(scope)``
Returns ``{"risks": [...], "opportunities": [...]}`` ready for DB persistence.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid as _uuid
from datetime import date, timedelta
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.risk_engine import compute_risk
from app.database import SessionLocal
from app.schemas.weather_agent import (
    DayRiskSnapshot,
    DayWeatherSnapshot,
    RiskLevel,
    RiskSummary,
)
from app.services.agent_types import OemScope
from app.services.langchain_llm import get_chat_model
from app.services.llm_client import _persist_llm_log
from app.services.oems import get_oem_by_id
from app.services.suppliers import get_by_id as get_supplier_by_id
from app.services.weather_service import (
    get_current_weather,
    get_forecast,
    get_historical_weather,
)
from app.services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

# Default transit days when not determinable from metadata.
DEFAULT_TRANSIT_DAYS = 7


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------

async def _broadcast_progress(
    step: str,
    message: str,
    details: dict | None = None,
    oem_name: str | None = None,
    supplier_name: str | None = None,
) -> None:
    """Broadcast a shipment weather agent progress event over websocket."""
    payload: dict = {
        "type": "shipment_weather_agent_progress",
        "step": step,
        "message": message,
    }
    if oem_name:
        payload["oemName"] = oem_name
    if supplier_name:
        payload["supplierName"] = supplier_name
    if details:
        payload["details"] = details
    await ws_manager.broadcast(payload)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class ShipmentWeatherState(TypedDict, total=False):
    scope: OemScope

    # Resolved city names (from DB or scope fallback)
    supplier_city: str
    oem_city: str
    oem_name: str | None
    supplier_name: str | None
    transit_days: int
    shipment_start_date: str  # YYYY-MM-DD

    # Forecast data fetched in parallel
    supplier_forecast: dict | None
    oem_forecast: dict | None

    # Day-by-day timeline built from weather data + risk engine
    day_results: list[dict]  # serialised DayRiskSnapshot dicts
    exposure_payload: dict  # full risk_analysis_payload

    # Final outputs (DB-ready)
    weather_risks: list[dict]
    weather_opportunities: list[dict]

    # Optional LLM summary
    agent_summary: str | None


# ---------------------------------------------------------------------------
# Waypoint interpolation (reused from shipment_weather.py)
# ---------------------------------------------------------------------------

def _interpolate_waypoints(supplier: str, oem: str, transit_days: int) -> list[str]:
    locations = []
    for i in range(transit_days):
        if i == 0:
            locations.append(supplier)
        elif i == transit_days - 1:
            locations.append(oem)
        else:
            midpoint = transit_days // 2
            city = supplier if i < midpoint else oem
            locations.append(city)
    return locations


# ---------------------------------------------------------------------------
# Weather snapshot helpers (reused from shipment_weather.py)
# ---------------------------------------------------------------------------

def _extract_day_weather_from_forecast(
    forecast_data: dict, target_date: str, day_number: int,
    location_label: str, city_used: str,
) -> DayWeatherSnapshot | None:
    try:
        forecast_days = forecast_data.get("forecast", {}).get("forecastday", [])
        for fd in forecast_days:
            if fd.get("date") == target_date:
                day = fd.get("day", {})
                cond = day.get("condition", {})
                return DayWeatherSnapshot(
                    date=target_date, day_number=day_number,
                    location_name=location_label, estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    temp_c=float(day.get("avgtemp_c", 0)),
                    min_temp_c=float(day.get("mintemp_c", 0)),
                    max_temp_c=float(day.get("maxtemp_c", 0)),
                    wind_kph=float(day.get("maxwind_kph", 0)),
                    precip_mm=float(day.get("totalprecip_mm", 0)),
                    vis_km=float(day.get("avgvis_km", 10)),
                    humidity=int(day.get("avghumidity", 50)),
                    is_historical=False,
                )
    except Exception as e:
        logger.warning("Failed to extract forecast day for %s: %s", target_date, e)
    return None


def _extract_day_weather_from_history(
    hist_data: dict, target_date: str, day_number: int,
    location_label: str, city_used: str,
) -> DayWeatherSnapshot | None:
    try:
        forecast_days = hist_data.get("forecast", {}).get("forecastday", [])
        for fd in forecast_days:
            if fd.get("date") == target_date:
                day = fd.get("day", {})
                cond = day.get("condition", {})
                return DayWeatherSnapshot(
                    date=target_date, day_number=day_number,
                    location_name=location_label, estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    temp_c=float(day.get("avgtemp_c", 0)),
                    min_temp_c=float(day.get("mintemp_c", 0)),
                    max_temp_c=float(day.get("maxtemp_c", 0)),
                    wind_kph=float(day.get("maxwind_kph", 0)),
                    precip_mm=float(day.get("totalprecip_mm", 0)),
                    vis_km=float(day.get("avgvis_km", 10)),
                    humidity=int(day.get("avghumidity", 50)),
                    is_historical=True,
                )
    except Exception as e:
        logger.warning("Failed to extract history day for %s: %s", target_date, e)
    return None


def _weather_snapshot_to_current_dict(snap: DayWeatherSnapshot) -> dict:
    return {
        "temp_c": snap.temp_c,
        "feelslike_c": snap.temp_c,
        "wind_kph": snap.wind_kph,
        "gust_kph": snap.wind_kph * 1.3,
        "precip_mm": snap.precip_mm,
        "vis_km": snap.vis_km,
        "humidity": snap.humidity,
        "cloud": 50,
        "pressure_mb": 1013,
        "uv": 5,
        "condition": {"code": 1000, "text": snap.condition},
    }


# ---------------------------------------------------------------------------
# Node 1: Resolve cities from scope / DB
# ---------------------------------------------------------------------------

async def _resolve_cities_node(state: ShipmentWeatherState) -> ShipmentWeatherState:
    """
    Extract supplier and OEM city names from the scope.
    Falls back to DB lookup if cities list is incomplete.
    """
    scope = state["scope"]
    oem_name = scope.get("oemName") or "Unknown OEM"
    supplier_name = scope.get("supplierName") or "Unknown Supplier"

    cities = scope.get("cities") or []
    # By convention: cities[0] = OEM city, cities[1] = supplier city
    oem_city = cities[0] if len(cities) > 0 else None
    supplier_city = cities[1] if len(cities) > 1 else None

    # Fallback: look up from DB if cities not in scope
    if not oem_city or not supplier_city:
        db = SessionLocal()
        try:
            oem_id_str = scope.get("oemId")
            supplier_id_str = scope.get("supplierId")
            if oem_id_str and not oem_city:
                from uuid import UUID
                oem_obj = get_oem_by_id(db, UUID(oem_id_str))
                if oem_obj and oem_obj.city:
                    oem_city = oem_obj.city
            if supplier_id_str and not supplier_city:
                from uuid import UUID
                sup_obj = get_supplier_by_id(db, UUID(supplier_id_str))
                if sup_obj and sup_obj.city:
                    supplier_city = sup_obj.city
        finally:
            db.close()

    # Ultimate fallback
    if not oem_city:
        oem_city = "New York"
    if not supplier_city:
        supplier_city = oem_city

    # Determine transit days (default 7)
    transit_days = DEFAULT_TRANSIT_DAYS
    shipment_start_date = date.today().strftime("%Y-%m-%d")

    logger.info(
        "[ShipmentWeatherGraph] Resolved cities: supplier=%s oem=%s transit=%d start=%s",
        supplier_city, oem_city, transit_days, shipment_start_date,
    )
    await _broadcast_progress(
        "resolve_cities",
        f"Route: {supplier_city} -> {oem_city} ({transit_days} days)",
        {"supplier_city": supplier_city, "oem_city": oem_city, "transit_days": transit_days},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    return {
        "supplier_city": supplier_city,
        "oem_city": oem_city,
        "oem_name": oem_name,
        "supplier_name": supplier_name,
        "transit_days": transit_days,
        "shipment_start_date": shipment_start_date,
    }


# ---------------------------------------------------------------------------
# Node 2: Fetch forecasts in parallel
# ---------------------------------------------------------------------------

async def _fetch_forecasts_node(state: ShipmentWeatherState) -> ShipmentWeatherState:
    """Fetch weather forecasts for both supplier and OEM cities in parallel."""
    supplier_city = state["supplier_city"]
    oem_city = state["oem_city"]
    transit_days = state.get("transit_days", DEFAULT_TRANSIT_DAYS)
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    today = date.today()
    start_date = date.today()  # shipment starts today
    forecast_days_needed = max(0, (start_date + timedelta(days=transit_days - 1) - today).days + 1)
    forecast_days_needed = min(forecast_days_needed + 1, 14)

    logger.info(
        "[ShipmentWeatherGraph] Fetching forecasts: supplier=%s oem=%s days=%d",
        supplier_city, oem_city, forecast_days_needed,
    )
    await _broadcast_progress(
        "fetch_forecasts",
        f"Fetching weather forecasts for {supplier_city} and {oem_city}",
        {"forecast_days": forecast_days_needed},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    try:
        supplier_forecast, oem_forecast = await asyncio.gather(
            get_forecast(supplier_city, days=forecast_days_needed),
            get_forecast(oem_city, days=forecast_days_needed),
        )
        logger.info(
            "[ShipmentWeatherGraph] Forecasts fetched: supplier=%s oem=%s",
            "ok" if supplier_forecast else "empty",
            "ok" if oem_forecast else "empty",
        )
        await _broadcast_progress(
            "fetch_forecasts_done",
            f"Weather forecasts retrieved for both cities",
            oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[ShipmentWeatherGraph] Forecast fetch error: %s", exc)
        await _broadcast_progress(
            "fetch_forecasts_error", f"Forecast fetch error: {exc}",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        supplier_forecast, oem_forecast = None, None

    return {
        "supplier_forecast": supplier_forecast,
        "oem_forecast": oem_forecast,
    }


# ---------------------------------------------------------------------------
# Node 3: Build daily timeline with risk scores
# ---------------------------------------------------------------------------

async def _build_daily_timeline_node(state: ShipmentWeatherState) -> ShipmentWeatherState:
    """
    Build a day-by-day weather timeline with per-day risk scores.
    Uses current weather for today, historical for past, forecast for future.
    """
    supplier_city = state["supplier_city"]
    oem_city = state["oem_city"]
    transit_days = state.get("transit_days", DEFAULT_TRANSIT_DAYS)
    shipment_start_date = state.get("shipment_start_date", date.today().strftime("%Y-%m-%d"))
    supplier_forecast = state.get("supplier_forecast")
    oem_forecast = state.get("oem_forecast")
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    today = date.today()
    start_date = date.fromisoformat(shipment_start_date)
    waypoints = _interpolate_waypoints(supplier_city, oem_city, transit_days)

    await _broadcast_progress(
        "build_timeline",
        f"Analyzing {transit_days}-day weather timeline",
        {"transit_days": transit_days},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    day_results: list[DayRiskSnapshot] = []

    for i, waypoint_city in enumerate(waypoints):
        day_number = i + 1
        target_date = start_date + timedelta(days=i)
        target_date_str = target_date.strftime("%Y-%m-%d")

        is_past = target_date < today
        is_today = target_date == today

        location_label = (
            f"{supplier_city} (Origin)" if i == 0
            else f"{oem_city} (Destination)" if i == transit_days - 1
            else f"In Transit - Day {day_number}"
        )

        weather_snap: DayWeatherSnapshot | None = None
        city_used = waypoint_city

        if is_today:
            raw = await get_current_weather(waypoint_city)
            if raw:
                current = raw.get("current", {})
                cond = current.get("condition", {})
                weather_snap = DayWeatherSnapshot(
                    date=target_date_str, day_number=day_number,
                    location_name=location_label, estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    temp_c=float(current.get("temp_c", 0)),
                    min_temp_c=None, max_temp_c=None,
                    wind_kph=float(current.get("wind_kph", 0)),
                    precip_mm=float(current.get("precip_mm", 0)),
                    vis_km=float(current.get("vis_km", 10)),
                    humidity=int(current.get("humidity", 50)),
                    is_historical=False,
                )
        elif is_past:
            hist_data = await get_historical_weather(waypoint_city, target_date_str)
            if hist_data:
                weather_snap = _extract_day_weather_from_history(
                    hist_data, target_date_str, day_number, location_label, city_used,
                )
        else:
            midpoint = transit_days // 2
            forecast_data = supplier_forecast if i < midpoint else oem_forecast
            if forecast_data:
                weather_snap = _extract_day_weather_from_forecast(
                    forecast_data, target_date_str, day_number, location_label, city_used,
                )
            if not weather_snap:
                fresh_forecast = await get_forecast(waypoint_city, days=14)
                if fresh_forecast:
                    weather_snap = _extract_day_weather_from_forecast(
                        fresh_forecast, target_date_str, day_number, location_label, city_used,
                    )

        if not weather_snap:
            weather_snap = DayWeatherSnapshot(
                date=target_date_str, day_number=day_number,
                location_name=location_label, estimated_location=city_used,
                condition="Data unavailable",
                temp_c=25.0, min_temp_c=None, max_temp_c=None,
                wind_kph=10.0, precip_mm=0.0, vis_km=10.0,
                humidity=50, is_historical=is_past,
            )

        current_dict = _weather_snapshot_to_current_dict(weather_snap)
        risk_raw = compute_risk({"current": current_dict})
        factors_serialized = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in risk_raw.get("factors", [])
        ]
        risk_dict_serialized = {**risk_raw, "factors": factors_serialized}
        if hasattr(risk_dict_serialized.get("overall_level"), "value"):
            risk_dict_serialized["overall_level"] = risk_dict_serialized["overall_level"].value
        for f in risk_dict_serialized["factors"]:
            if hasattr(f.get("level"), "value"):
                f["level"] = f["level"].value

        risk_summary = RiskSummary(**risk_dict_serialized)

        concern_text = (
            risk_summary.primary_concerns[0]
            if risk_summary.primary_concerns
            else "No significant risk"
        )
        risk_summary_text = (
            f"Day {day_number} ({target_date_str}): {location_label} — "
            f"{weather_snap.condition}, {weather_snap.temp_c:.1f}C, wind {weather_snap.wind_kph:.0f} km/h. "
            f"Risk: {risk_summary.overall_level} ({risk_summary.overall_score:.0f}/100). {concern_text}"
        )

        day_results.append(
            DayRiskSnapshot(
                date=target_date_str, day_number=day_number,
                location_name=location_label, weather=weather_snap,
                risk=risk_summary, risk_summary_text=risk_summary_text,
            )
        )

    # Build exposure payload
    all_scores = [d.risk.overall_score for d in day_results]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    max_score = max(all_scores) if all_scores else 0
    exposure_score = round(max_score * 0.5 + avg_score * 0.5, 1) if all_scores else 0.0

    peak_risk_day = max(day_results, key=lambda d: d.risk.overall_score) if day_results else None
    high_risk_days = [
        d for d in day_results
        if d.risk.overall_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    ]

    factor_names = ["transportation", "power_outage", "production", "port_and_route", "raw_material_delay"]
    factor_max_scores: dict[str, float] = {f: 0.0 for f in factor_names}
    for d in day_results:
        for factor in d.risk.factors:
            fn = factor.factor
            if fn in factor_max_scores:
                factor_max_scores[fn] = max(factor_max_scores[fn], factor.score)

    all_concerns: list[str] = []
    all_actions: list[str] = []
    for d in day_results:
        all_concerns.extend(d.risk.primary_concerns)
        all_actions.extend(d.risk.suggested_actions)

    exposure_payload = {
        "shipment_metadata": {
            "supplier_city": supplier_city,
            "oem_city": oem_city,
            "start_date": shipment_start_date,
            "transit_days": transit_days,
        },
        "exposure_summary": {
            "average_risk_score": round(avg_score, 1),
            "peak_risk_score": round(peak_risk_day.risk.overall_score, 1) if peak_risk_day else 0,
            "peak_risk_day": peak_risk_day.day_number if peak_risk_day else None,
            "peak_risk_date": peak_risk_day.date if peak_risk_day else None,
            "high_risk_day_count": len(high_risk_days),
            "high_risk_dates": [d.date for d in high_risk_days],
            "overall_exposure_score": exposure_score,
        },
        "risk_factors_max": factor_max_scores,
        "primary_concerns": list(dict.fromkeys(all_concerns))[:6],
        "recommended_actions": list(dict.fromkeys(all_actions))[:6],
        "daily_timeline": [
            {
                "day": d.day_number, "date": d.date,
                "location": d.location_name,
                "is_historical": d.weather.is_historical,
                "weather": {
                    "condition": d.weather.condition,
                    "temp_c": d.weather.temp_c,
                    "wind_kph": d.weather.wind_kph,
                    "precip_mm": d.weather.precip_mm,
                    "vis_km": d.weather.vis_km,
                    "humidity": d.weather.humidity,
                },
                "risk_score": d.risk.overall_score,
                "risk_level": d.risk.overall_level,
                "key_concern": d.risk.primary_concerns[0] if d.risk.primary_concerns else "No significant risk",
            }
            for d in day_results
        ],
    }

    # Serialize day_results for state transport
    day_results_dicts = [d.model_dump() for d in day_results]

    logger.info(
        "[ShipmentWeatherGraph] Timeline built: %d days, exposure_score=%.1f, high_risk_days=%d",
        len(day_results), exposure_score, len(high_risk_days),
    )
    await _broadcast_progress(
        "timeline_built",
        f"Weather timeline: {len(day_results)} days analyzed, exposure score {exposure_score:.0f}/100",
        {
            "transit_days": transit_days,
            "exposure_score": exposure_score,
            "high_risk_days": len(high_risk_days),
        },
        oem_name=state.get("oem_name"), supplier_name=state.get("supplier_name"),
    )

    return {
        "day_results": day_results_dicts,
        "exposure_payload": exposure_payload,
    }


# ---------------------------------------------------------------------------
# Node 4: Build risk/opportunity dicts from exposure data
# ---------------------------------------------------------------------------

async def _build_exposure_risks_node(state: ShipmentWeatherState) -> ShipmentWeatherState:
    """
    Convert the exposure payload into structured risk and opportunity dicts
    ready for DB persistence.
    """
    payload = state.get("exposure_payload") or {}
    summary = payload.get("exposure_summary") or {}
    supplier_city = state.get("supplier_city", "Unknown")
    oem_city = state.get("oem_city", "Unknown")
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    exposure_score = summary.get("overall_exposure_score", 0)
    peak_score = summary.get("peak_risk_score", 0)
    high_risk_count = summary.get("high_risk_day_count", 0)
    peak_day = summary.get("peak_risk_day")
    peak_date = summary.get("peak_risk_date")
    concerns = payload.get("primary_concerns") or []
    actions = payload.get("recommended_actions") or []

    risks: list[dict] = []
    opportunities: list[dict] = []

    # Determine severity from exposure score
    if exposure_score >= 75:
        severity = "critical"
    elif exposure_score >= 50:
        severity = "high"
    elif exposure_score >= 25:
        severity = "medium"
    else:
        severity = "low"

    if exposure_score > 10:
        concern_text = "; ".join(concerns[:3]) if concerns else "Weather exposure along transit route"
        action_text = "; ".join(actions[:3]) if actions else "Monitor weather conditions"

        risks.append({
            "title": f"Weather exposure on {supplier_city} to {oem_city} route",
            "description": (
                f"Shipment route from {supplier_city} to {oem_city} has "
                f"an overall weather exposure score of {exposure_score:.0f}/100. "
                f"Peak risk of {peak_score:.0f}/100 on Day {peak_day} ({peak_date}). "
                f"{high_risk_count} high/critical risk day(s) identified. "
                f"Key concerns: {concern_text}."
            ),
            "severity": severity,
            "affectedRegion": f"{supplier_city} - {oem_city}",
            "affectedSupplier": supplier_name,
            "estimatedImpact": action_text,
            "estimatedCost": None,
            "sourceType": "weather",
            "sourceData": {
                "weatherExposure": {
                    "weather_exposure_score": exposure_score,
                    "peak_risk_score": peak_score,
                    "peak_risk_day": peak_day,
                    "high_risk_day_count": high_risk_count,
                    "route": f"{supplier_city} -> {oem_city}",
                },
                "risk_factors_max": payload.get("risk_factors_max", {}),
            },
        })

        # Add per-day risks for high/critical days
        for day_entry in (payload.get("daily_timeline") or []):
            day_score = day_entry.get("risk_score", 0)
            day_level = day_entry.get("risk_level", "low")
            if isinstance(day_level, RiskLevel):
                day_level = day_level.value
            if day_level in ("high", "critical"):
                risks.append({
                    "title": f"High weather risk on Day {day_entry['day']} ({day_entry['date']})",
                    "description": (
                        f"Weather at {day_entry['location']}: {day_entry['weather']['condition']}, "
                        f"{day_entry['weather']['temp_c']}C, wind {day_entry['weather']['wind_kph']} km/h. "
                        f"Risk score: {day_score:.0f}/100. {day_entry.get('key_concern', '')}"
                    ),
                    "severity": "critical" if day_score >= 75 else "high",
                    "affectedRegion": day_entry["location"],
                    "affectedSupplier": supplier_name,
                    "estimatedImpact": f"Potential delay on transit day {day_entry['day']}",
                    "estimatedCost": None,
                    "sourceType": "weather",
                    "sourceData": {
                        "weatherExposure": {
                            "weather_exposure_score": day_score,
                            "day_number": day_entry["day"],
                            "date": day_entry["date"],
                            "location": day_entry["location"],
                        },
                    },
                })
    else:
        opportunities.append({
            "title": f"Favorable weather window for {supplier_city} to {oem_city} route",
            "description": (
                f"Weather conditions along the {supplier_city} to {oem_city} "
                f"transit route appear stable with low exposure score of {exposure_score:.0f}/100."
            ),
            "type": "time_saving",
            "affectedRegion": f"{supplier_city} - {oem_city}",
            "potentialBenefit": "Opportunity to prioritize shipments while conditions are favorable.",
            "estimatedValue": None,
            "sourceType": "weather",
            "sourceData": {
                "weatherExposure": {
                    "weather_exposure_score": exposure_score,
                    "route": f"{supplier_city} -> {oem_city}",
                },
            },
        })

    logger.info(
        "[ShipmentWeatherGraph] Exposure risks built: risks=%d opportunities=%d",
        len(risks), len(opportunities),
    )
    await _broadcast_progress(
        "exposure_risks_built",
        f"Weather analysis: {len(risks)} risks, {len(opportunities)} opportunities",
        {"risks": len(risks), "opportunities": len(opportunities)},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    return {
        "weather_risks": risks,
        "weather_opportunities": opportunities,
    }


# ---------------------------------------------------------------------------
# Node 5: LLM summary (optional, with fallback)
# ---------------------------------------------------------------------------

_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a supply chain risk analyst specializing in weather-related transit risks.",
    ),
    (
        "user",
        (
            "A shipment is travelling from {supplier_city} to {oem_city} "
            "over {transit_days} days starting {start_date}.\n\n"
            "Exposure summary:\n{exposure_json}\n\n"
            "Write a concise executive summary (3-5 sentences) for an OEM operations manager: "
            "highlight the worst weather windows, which days/legs are most exposed, "
            "and top 2-3 mitigation actions. Keep it under 400 characters."
        ),
    ),
])


async def _llm_summary_node(state: ShipmentWeatherState) -> ShipmentWeatherState:
    """Generate an optional LLM executive summary for the weather exposure."""
    payload = state.get("exposure_payload") or {}
    supplier_city = state.get("supplier_city", "Unknown")
    oem_city = state.get("oem_city", "Unknown")
    transit_days = state.get("transit_days", DEFAULT_TRANSIT_DAYS)
    start_date = state.get("shipment_start_date", "")
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    import json
    exposure_json = json.dumps(payload.get("exposure_summary", {}), indent=2)

    llm = get_chat_model()
    if not llm:
        summary = _fallback_summary(payload, supplier_city, oem_city)
        logger.info("[ShipmentWeatherGraph] LLM unavailable, using fallback summary")
        return {"agent_summary": summary}

    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]
    start = time.perf_counter()

    prompt_text = _SUMMARY_PROMPT.format(
        supplier_city=supplier_city, oem_city=oem_city,
        transit_days=transit_days, start_date=start_date,
        exposure_json=exposure_json,
    )

    try:
        await _broadcast_progress(
            "llm_summary_start",
            f"Generating weather risk summary via {provider}",
            {"provider": provider, "model": str(model_name)},
            oem_name=oem_name, supplier_name=supplier_name,
        )

        chain = _SUMMARY_PROMPT | llm
        msg = await chain.ainvoke({
            "supplier_city": supplier_city,
            "oem_city": oem_city,
            "transit_days": str(transit_days),
            "start_date": start_date,
            "exposure_json": exposure_json,
        })

        elapsed = int((time.perf_counter() - start) * 1000)
        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block))
            raw_text = "".join(parts)

        logger.info(
            "[ShipmentWeatherGraph] LLM summary id=%s provider=%s elapsed_ms=%d len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, raw_text, "success", elapsed, None,
        )

        summary = raw_text.strip() or _fallback_summary(payload, supplier_city, oem_city)

        await _broadcast_progress(
            "llm_summary_done",
            "Weather risk summary generated",
            {"elapsed_ms": elapsed},
            oem_name=oem_name, supplier_name=supplier_name,
        )

        return {"agent_summary": summary}

    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[ShipmentWeatherGraph] LLM summary error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, None, "error", elapsed, str(exc),
        )
        await _broadcast_progress(
            "llm_summary_error", f"LLM summary failed, using fallback: {exc}",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"agent_summary": _fallback_summary(payload, supplier_city, oem_city)}


def _fallback_summary(payload: dict, supplier_city: str, oem_city: str) -> str:
    """Rule-based fallback summary when LLM is unavailable."""
    summary_data = payload.get("exposure_summary") or {}
    avg = summary_data.get("average_risk_score", 0)
    peak = summary_data.get("peak_risk_score", 0)
    peak_day = summary_data.get("peak_risk_day")
    high_count = summary_data.get("high_risk_day_count", 0)
    score = summary_data.get("overall_exposure_score", 0)

    parts = [
        f"Weather exposure score for {supplier_city} to {oem_city} route: {score:.0f}/100.",
    ]
    if peak_day:
        parts.append(f"Peak risk on Day {peak_day} (score {peak:.0f}/100).")
    if high_count:
        parts.append(f"{high_count} high/critical risk day(s) require monitoring.")
    parts.append(f"Average daily risk score: {avg:.0f}/100.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(ShipmentWeatherState)

_builder.add_node("resolve_cities", _resolve_cities_node)
_builder.add_node("fetch_forecasts", _fetch_forecasts_node)
_builder.add_node("build_daily_timeline", _build_daily_timeline_node)
_builder.add_node("build_exposure_risks", _build_exposure_risks_node)
_builder.add_node("llm_summary", _llm_summary_node)

_builder.set_entry_point("resolve_cities")
_builder.add_edge("resolve_cities", "fetch_forecasts")
_builder.add_edge("fetch_forecasts", "build_daily_timeline")
_builder.add_edge("build_daily_timeline", "build_exposure_risks")
_builder.add_edge("build_exposure_risks", "llm_summary")
_builder.add_edge("llm_summary", END)

SHIPMENT_WEATHER_GRAPH = _builder.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def run_shipment_weather_graph(
    scope: OemScope,
) -> dict[str, list[dict]]:
    """
    Orchestrate the Shipment Weather Exposure Agent using LangGraph.

    Resolves supplier/OEM cities from scope, fetches weather forecasts,
    builds a day-by-day risk timeline, and produces structured risks
    and opportunities ready for DB persistence.

    Returns ``{"risks": [...], "opportunities": [...]}``
    """
    oem_label = scope.get("oemName") or "unknown"
    supplier_label = scope.get("supplierName") or "unknown"
    entity_label = f"{oem_label}/{supplier_label}"

    logger.info("[ShipmentWeatherGraph] Starting for %s", entity_label)
    await _broadcast_progress(
        "started",
        f"Starting shipment weather analysis for {entity_label}",
        {"oem": oem_label, "supplier": supplier_label},
        oem_name=oem_label, supplier_name=supplier_label,
    )

    initial_state: ShipmentWeatherState = {
        "scope": scope,
    }

    final_state = await SHIPMENT_WEATHER_GRAPH.ainvoke(initial_state)

    risks = final_state.get("weather_risks") or []
    opps = final_state.get("weather_opportunities") or []

    logger.info(
        "[ShipmentWeatherGraph] Completed for %s: risks=%d opportunities=%d",
        entity_label, len(risks), len(opps),
    )
    await _broadcast_progress(
        "completed",
        f"Shipment weather analysis complete: {len(risks)} risks, {len(opps)} opportunities",
        {"risks": len(risks), "opportunities": len(opps)},
        oem_name=oem_label, supplier_name=supplier_label,
    )

    return {"risks": risks, "opportunities": opps}
