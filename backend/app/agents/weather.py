"""
Weather Exposure Graph Agent
============================
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
  [llm_summary]          <- optional LLM executive summary
      |
      v
     END

Public entrypoint: ``run_weather_graph(scope)``
Returns ``{"risks": [...], "opportunities": [...]}`` ready for DB persistence.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid as _uuid
from datetime import date, timedelta
from typing import TypedDict

import httpx

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
# Shipment tracking API helper
# ---------------------------------------------------------------------------

async def _fetch_shipment_tracking(supplier_id: str) -> dict | None:
    """
    Fetch shipment tracking data from the mock API for a given supplier.

    Returns ``items[0]["data"]`` which contains:
      - ``supplier_name``
      - ``tracking_data`` → ``{route_plan, shipment_meta}``

    Returns None when the env var is missing, supplier_id is empty, or the
    call fails.
    """
    from app.config import settings as _settings
    base_url = _settings.mock_server_base_url
    if not supplier_id:
        logger.debug("[WeatherGraph] _fetch_shipment_tracking: supplier_id is empty — skipping")
        return None
    if not base_url:
        logger.warning(
            "[WeatherGraph] MOCK_SERVER_BASE_URL is not configured — "
            "shipment tracking will not be fetched; transit_days/route_plan will use defaults"
        )
        return None
    url = f"{base_url.rstrip('/')}/mock/shipment-tracking"
    logger.info("[WeatherGraph] Fetching shipment tracking: supplier=%s url=%s", supplier_id, url)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params={"q": f"supplier_id:{supplier_id}"})
            r.raise_for_status()
            data = r.json()
            items = data.get("items") or []
            if not items:
                logger.warning(
                    "[WeatherGraph] No shipment tracking items for supplier=%s", supplier_id
                )
                return None
            item_data = items[0].get("data") or {}
            tracking = item_data.get("tracking_data") or {}
            route_plan = tracking.get("route_plan") or []
            meta = tracking.get("shipment_meta") or {}
            logger.info(
                "[WeatherGraph] Shipment tracking OK: supplier=%s name=%s "
                "transit_days=%s pickup=%s route_stops=%d",
                supplier_id,
                item_data.get("supplier_name", "?"),
                meta.get("transit_days_estimated", "?"),
                (meta.get("pickup_date") or "")[:10],
                len(route_plan),
            )
            return item_data  # caller reads .supplier_name + .tracking_data
    except Exception as exc:
        logger.warning(
            "[WeatherGraph] Shipment tracking fetch failed for supplier=%s: %s",
            supplier_id, exc,
        )
        return None


def _get_city_for_date_from_route(
    route_plan: list[dict], target_date: date
) -> tuple[str, str] | None:
    """
    Return ``(city, transport_mode_of_next_leg)`` for *target_date* based on
    the actual route plan waypoints.

    Logic: the shipment is at the most recent waypoint whose arrival date
    (actual or planned) is <= target_date.  The transport_mode of the *next*
    waypoint describes how it travels out of that stop.
    """
    sorted_plan = sorted(route_plan, key=lambda x: x.get("sequence", 0))
    if not sorted_plan:
        return None

    current_idx = -1
    for i, wp in enumerate(sorted_plan):
        arr_str = wp.get("actual_arrival") or wp.get("planned_arrival") or ""
        if not arr_str:
            continue
        try:
            arr_date = date.fromisoformat(arr_str[:10])
        except ValueError:
            continue
        if arr_date <= target_date:
            current_idx = i
        else:
            break

    if current_idx == -1:
        # Before any recorded arrival — use origin city
        loc = sorted_plan[0].get("location", {})
        return loc.get("city", ""), ""

    wp = sorted_plan[current_idx]
    city = wp.get("location", {}).get("city", "")
    # transport_mode of the NEXT leg (how we leave this waypoint)
    next_mode = ""
    if current_idx + 1 < len(sorted_plan):
        next_mode = sorted_plan[current_idx + 1].get("transport_mode", "")
    return city, next_mode


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
    """Broadcast a weather agent progress event over websocket."""
    payload: dict = {
        "type": "weather_agent_progress",
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

class WeatherState(TypedDict, total=False):
    scope: OemScope

    # Resolved city names (from DB or scope fallback)
    supplier_city: str
    oem_city: str
    oem_name: str | None
    supplier_name: str | None
    transit_days: int
    shipment_start_date: str  # YYYY-MM-DD

    # Shipment route plan from tracking API (actual waypoints)
    route_plan: list[dict] | None

    # Forecast data fetched in parallel
    supplier_forecast: dict | None
    oem_forecast: dict | None
    route_city_forecasts: dict[str, dict] | None  # city → forecast data for all route cities

    # Day-by-day timeline built from weather data + risk engine
    day_results: list[dict]  # serialised DayRiskSnapshot dicts
    exposure_payload: dict  # full risk_analysis_payload

    # Final outputs (DB-ready)
    weather_risks: list[dict]
    weather_opportunities: list[dict]

    # Optional LLM summary
    agent_summary: str | None


# ---------------------------------------------------------------------------
# Waypoint interpolation
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
# Weather snapshot helpers
# ---------------------------------------------------------------------------

def _extract_peak_hourly_gust(fd: dict) -> float | None:
    """Extract peak gust_kph from hourly data for a forecast day."""
    hours = fd.get("hour") or []
    if not hours:
        return None
    gusts = [float(h.get("gust_kph", 0)) for h in hours if h.get("gust_kph")]
    return max(gusts) if gusts else None


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
                peak_gust = _extract_peak_hourly_gust(fd)
                return DayWeatherSnapshot(
                    date=target_date, day_number=day_number,
                    location_name=location_label, estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    condition_code=int(cond.get("code", 1000)),
                    temp_c=float(day.get("avgtemp_c", 0)),
                    min_temp_c=float(day.get("mintemp_c", 0)),
                    max_temp_c=float(day.get("maxtemp_c", 0)),
                    wind_kph=float(day.get("maxwind_kph", 0)),
                    gust_kph=peak_gust,
                    precip_mm=float(day.get("totalprecip_mm", 0)),
                    snow_cm=float(day.get("totalsnow_cm", 0)),
                    vis_km=float(day.get("avgvis_km", 10)),
                    humidity=int(day.get("avghumidity", 50)),
                    uv=float(day.get("uv", 0)) if day.get("uv") is not None else None,
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
                peak_gust = _extract_peak_hourly_gust(fd)
                return DayWeatherSnapshot(
                    date=target_date, day_number=day_number,
                    location_name=location_label, estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    condition_code=int(cond.get("code", 1000)),
                    temp_c=float(day.get("avgtemp_c", 0)),
                    min_temp_c=float(day.get("mintemp_c", 0)),
                    max_temp_c=float(day.get("maxtemp_c", 0)),
                    wind_kph=float(day.get("maxwind_kph", 0)),
                    gust_kph=peak_gust,
                    precip_mm=float(day.get("totalprecip_mm", 0)),
                    snow_cm=float(day.get("totalsnow_cm", 0)),
                    vis_km=float(day.get("avgvis_km", 10)),
                    humidity=int(day.get("avghumidity", 50)),
                    uv=float(day.get("uv", 0)) if day.get("uv") is not None else None,
                    is_historical=True,
                )
    except Exception as e:
        logger.warning("Failed to extract history day for %s: %s", target_date, e)
    return None


def _get_last_forecast_day(
    forecast_data: dict, day_number: int, location_label: str,
    city_used: str, target_date_str: str,
) -> DayWeatherSnapshot | None:
    """
    When *target_date* is beyond the forecast window (WeatherAPI cap: 14 days),
    return the *last* available forecast day's data as a best-effort estimate.
    The ``date`` field is set to the actual target date so the timeline stays
    continuous.  ``is_estimated`` is set True to flag data quality downstream.
    """
    try:
        forecast_days = forecast_data.get("forecast", {}).get("forecastday", [])
        if not forecast_days:
            return None
        last = forecast_days[-1]
        day = last.get("day", {})
        cond = day.get("condition", {})
        peak_gust = _extract_peak_hourly_gust(last)
        return DayWeatherSnapshot(
            date=target_date_str, day_number=day_number,
            location_name=location_label, estimated_location=city_used,
            condition=cond.get("text", "Unknown"),
            condition_code=int(cond.get("code", 1000)),
            temp_c=float(day.get("avgtemp_c", 0)),
            min_temp_c=float(day.get("mintemp_c", 0)),
            max_temp_c=float(day.get("maxtemp_c", 0)),
            wind_kph=float(day.get("maxwind_kph", 0)),
            gust_kph=peak_gust,
            precip_mm=float(day.get("totalprecip_mm", 0)),
            snow_cm=float(day.get("totalsnow_cm", 0)),
            vis_km=float(day.get("avgvis_km", 10)),
            humidity=int(day.get("avghumidity", 50)),
            uv=float(day.get("uv", 0)) if day.get("uv") is not None else None,
            is_historical=False,
            is_estimated=True,
        )
    except Exception as e:
        logger.warning("Failed to get last forecast day for %s: %s", target_date_str, e)
    return None


def _weather_snapshot_to_current_dict(snap: DayWeatherSnapshot) -> dict:
    """Convert a DayWeatherSnapshot into the dict format expected by compute_risk().

    Uses actual condition codes, gust data, and feels-like temperature when
    available — previously these were hardcoded, causing the risk engine to
    miss snow/ice, storms, and extreme wind conditions entirely.
    """
    return {
        "temp_c": snap.temp_c,
        "feelslike_c": snap.feelslike_c if snap.feelslike_c is not None else snap.temp_c,
        "wind_kph": snap.wind_kph,
        "gust_kph": snap.gust_kph if snap.gust_kph is not None else snap.wind_kph * 1.3,
        "precip_mm": snap.precip_mm,
        "vis_km": snap.vis_km,
        "humidity": snap.humidity,
        "uv": snap.uv,
        "condition": {"code": snap.condition_code, "text": snap.condition},
    }


# ---------------------------------------------------------------------------
# Node 1: Resolve cities from scope / DB
# ---------------------------------------------------------------------------

async def _resolve_cities_node(state: WeatherState) -> WeatherState:
    """
    Resolve supplier and OEM city names by looking up the DB directly
    using oemId / supplierId from the scope (same pattern as news agent).
    """
    scope = state["scope"]
    oem_name: str = scope.get("oemName") or ""
    supplier_name: str = scope.get("supplierName") or ""

    oem_city: str | None = None
    supplier_city: str | None = None

    db = SessionLocal()
    try:
        oem_id_str = scope.get("oemId")
        supplier_id_str = scope.get("supplierId")
        if oem_id_str:
            from uuid import UUID
            oem_obj = get_oem_by_id(db, UUID(oem_id_str))
            if oem_obj:
                oem_city = (
                    getattr(oem_obj, "city", None)
                    or getattr(oem_obj, "location", None)
                    or getattr(oem_obj, "country", None)
                )
                if not oem_name:
                    oem_name = (
                        getattr(oem_obj, "name", None)
                        or getattr(oem_obj, "company_name", None)
                        or ""
                    )
        if supplier_id_str:
            from uuid import UUID
            sup_obj = get_supplier_by_id(db, UUID(supplier_id_str))
            if sup_obj:
                supplier_city = (
                    getattr(sup_obj, "city", None)
                    or getattr(sup_obj, "location", None)
                    or getattr(sup_obj, "country", None)
                )
                if not supplier_name:
                    supplier_name = (
                        getattr(sup_obj, "name", None)
                        or getattr(sup_obj, "company_name", None)
                        or ""
                    )
    finally:
        db.close()

    logger.info(
        "[WeatherGraph] DB lookup: oem=%r city=%s supplier=%r city=%s",
        oem_name or "?", oem_city or "?", supplier_name or "?", supplier_city or "?",
    )

    # Always try the shipment tracking API when supplier_id is available:
    #   - fills transit_days / shipment_start_date (if not pre-set by caller)
    #   - always fills route_plan for route-aware weather analysis
    transit_days = state.get("transit_days") or 0
    shipment_start_date = state.get("shipment_start_date") or ""
    route_plan: list[dict] | None = None

    if supplier_id_str:
        item_data = await _fetch_shipment_tracking(supplier_id_str)
        if item_data:
            # Supplier name from tracking data (more reliable than DB for display)
            if not supplier_name:
                supplier_name = item_data.get("supplier_name") or ""
            tracking = item_data.get("tracking_data") or {}
            meta = tracking.get("shipment_meta") or {}
            if not transit_days:
                transit_days = int(meta.get("transit_days_estimated") or 0)
            if not shipment_start_date:
                pickup_raw = meta.get("pickup_date") or ""
                shipment_start_date = pickup_raw[:10] if pickup_raw else ""
            route_plan = tracking.get("route_plan") or None
            logger.info(
                "[WeatherGraph] Tracking resolved: transit_days=%d start=%s "
                "route_stops=%d supplier_name=%r",
                transit_days, shipment_start_date,
                len(route_plan) if route_plan else 0,
                supplier_name,
            )
            if route_plan:
                for wp in sorted(route_plan, key=lambda x: x.get("sequence", 0)):
                    loc = wp.get("location", {})
                    logger.info(
                        "[WeatherGraph]   waypoint seq=%s status=%-9s city=%s mode=%s",
                        wp.get("sequence", "?"),
                        wp.get("status", "?"),
                        loc.get("city", "?"),
                        wp.get("transport_mode", "?"),
                    )

    if not oem_city or not supplier_city:
        logger.warning(
            "[WeatherGraph] Cannot resolve cities (oem_city=%s, supplier_city=%s) — skipping",
            oem_city, supplier_city,
        )
        await _broadcast_progress(
            "resolve_cities_skipped",
            "Cannot resolve supplier/OEM cities — skipping weather analysis",
            oem_name=oem_name or "Unknown OEM",
            supplier_name=supplier_name or "Unknown Supplier",
        )
        return {
            "supplier_city": "",
            "oem_city": "",
            "oem_name": oem_name or "Unknown OEM",
            "supplier_name": supplier_name or "Unknown Supplier",
            "transit_days": 0,
            "shipment_start_date": date.today().strftime("%Y-%m-%d"),
            "route_plan": None,
        }

    if not transit_days:
        transit_days = DEFAULT_TRANSIT_DAYS
        logger.info("[WeatherGraph] transit_days not found — using default=%d", transit_days)
    if not shipment_start_date:
        shipment_start_date = date.today().strftime("%Y-%m-%d")
        logger.info("[WeatherGraph] shipment_start_date not found — using today=%s", shipment_start_date)

    oem_name = oem_name or "Unknown OEM"
    supplier_name = supplier_name or "Unknown Supplier"

    logger.info(
        "[WeatherGraph] Resolved: oem=%r city=%s supplier=%r city=%s transit=%d start=%s route=%s",
        oem_name, oem_city, supplier_name, supplier_city,
        transit_days, shipment_start_date,
        "yes" if route_plan else "no",
    )
    await _broadcast_progress(
        "resolve_cities",
        f"Route: {supplier_city} → {oem_city} ({transit_days} days) via {len(route_plan) if route_plan else 0} stops",
        {"supplier_city": supplier_city, "oem_city": oem_city, "transit_days": transit_days,
         "route_stops": len(route_plan) if route_plan else 0},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    return {
        "supplier_city": supplier_city,
        "oem_city": oem_city,
        "oem_name": oem_name,
        "supplier_name": supplier_name,
        "transit_days": transit_days,
        "shipment_start_date": shipment_start_date,
        "route_plan": route_plan,
    }


# ---------------------------------------------------------------------------
# Node 2: Fetch forecasts in parallel
# ---------------------------------------------------------------------------

async def _fetch_forecasts_node(state: WeatherState) -> WeatherState:
    """Fetch weather forecasts for all route cities (supplier, OEM, and waypoints) in parallel."""
    supplier_city = state["supplier_city"]
    oem_city = state["oem_city"]
    transit_days = state.get("transit_days", DEFAULT_TRANSIT_DAYS)
    route_plan = state.get("route_plan")
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    if not supplier_city or not oem_city:
        logger.info("[WeatherGraph] Cities not resolved — skipping forecast fetch")
        return {"supplier_forecast": None, "oem_forecast": None, "route_city_forecasts": {}}

    today = date.today()
    start_date_str = state.get("shipment_start_date") or today.strftime("%Y-%m-%d")
    start_date = date.fromisoformat(start_date_str)
    forecast_days_needed = max(0, (start_date + timedelta(days=transit_days - 1) - today).days + 1)
    forecast_days_needed = min(forecast_days_needed + 1, 14)

    # Collect all unique cities to fetch: supplier + oem + all route waypoints
    ordered_cities: list[str] = [supplier_city, oem_city]
    if route_plan:
        for wp in sorted(route_plan, key=lambda x: x.get("sequence", 0)):
            city = wp.get("location", {}).get("city") or ""
            if city and city not in ordered_cities:
                ordered_cities.append(city)

    logger.info(
        "[WeatherGraph] Fetching forecasts for %d cities: %s (days=%d)",
        len(ordered_cities), ordered_cities, forecast_days_needed,
    )
    await _broadcast_progress(
        "fetch_forecasts",
        f"Fetching weather forecasts for {len(ordered_cities)} route cities",
        {"cities": ordered_cities, "forecast_days": forecast_days_needed},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    try:
        results = await asyncio.gather(
            *[get_forecast(city, days=forecast_days_needed) for city in ordered_cities],
            return_exceptions=True,
        )
        supplier_forecast = results[0] if not isinstance(results[0], BaseException) else None
        oem_forecast = results[1] if len(results) > 1 and not isinstance(results[1], BaseException) else None

        route_city_forecasts: dict[str, dict] = {}
        for city, result in zip(ordered_cities, results):
            if isinstance(result, dict):
                route_city_forecasts[city] = result

        logger.info(
            "[WeatherGraph] Forecasts fetched: %d/%d cities ok",
            sum(1 for r in results if isinstance(r, dict)), len(ordered_cities),
        )
        await _broadcast_progress(
            "fetch_forecasts_done",
            f"Weather forecasts retrieved for {len(route_city_forecasts)} cities",
            oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[WeatherGraph] Forecast fetch error: %s", exc)
        await _broadcast_progress(
            "fetch_forecasts_error", f"Forecast fetch error: {exc}",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        supplier_forecast, oem_forecast, route_city_forecasts = None, None, {}

    return {
        "supplier_forecast": supplier_forecast,
        "oem_forecast": oem_forecast,
        "route_city_forecasts": route_city_forecasts,
    }


# ---------------------------------------------------------------------------
# Node 3: Build daily timeline with risk scores
# ---------------------------------------------------------------------------

async def _build_daily_timeline_node(state: WeatherState) -> WeatherState:
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

    route_plan = state.get("route_plan")
    route_city_forecasts = state.get("route_city_forecasts") or {}

    today = date.today()
    start_date = date.fromisoformat(shipment_start_date)

    # Use actual route waypoints when available, otherwise fall back to interpolation
    use_route = bool(route_plan)
    if not use_route:
        waypoints = _interpolate_waypoints(supplier_city, oem_city, transit_days)

    await _broadcast_progress(
        "build_timeline",
        f"Analyzing {transit_days}-day weather timeline"
        + (f" across {len(route_plan)} route stops" if route_plan else ""),
        {"transit_days": transit_days, "route_based": use_route},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    day_results: list[DayRiskSnapshot] = []

    for i in range(transit_days):
        day_number = i + 1
        target_date = start_date + timedelta(days=i)
        target_date_str = target_date.strftime("%Y-%m-%d")

        is_past = target_date < today
        is_today = target_date == today

        # --- Determine city and location label for this day ---
        if use_route:
            sorted_route = sorted(route_plan, key=lambda x: x.get("sequence", 0))
            if i == 0:
                # Always force origin = first route waypoint (ignore arrival-date logic)
                origin_wp = sorted_route[0]
                waypoint_city = origin_wp.get("location", {}).get("city", "") or supplier_city
                transport_mode = ""
                location_label = f"{waypoint_city} (Origin)"
            elif i == transit_days - 1:
                # Always force destination = last route waypoint
                dest_wp = sorted_route[-1]
                waypoint_city = dest_wp.get("location", {}).get("city", "") or oem_city
                transport_mode = ""
                location_label = f"{waypoint_city} (Destination)"
            else:
                route_result = _get_city_for_date_from_route(route_plan, target_date)
                if route_result:
                    waypoint_city, transport_mode = route_result
                else:
                    waypoint_city, transport_mode = supplier_city, ""
                if transport_mode:
                    location_label = f"In Transit via {transport_mode} - Day {day_number}"
                else:
                    location_label = f"In Transit - Day {day_number}"
        else:
            waypoint_city = waypoints[i]
            transport_mode = ""
            if i == 0:
                location_label = f"{supplier_city} (Origin)"
            elif i == transit_days - 1:
                location_label = f"{oem_city} (Destination)"
            else:
                location_label = f"In Transit - Day {day_number}"

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
                    condition_code=int(cond.get("code", 1000)),
                    temp_c=float(current.get("temp_c", 0)),
                    feelslike_c=float(current.get("feelslike_c", current.get("temp_c", 0))),
                    min_temp_c=None, max_temp_c=None,
                    wind_kph=float(current.get("wind_kph", 0)),
                    gust_kph=float(current.get("gust_kph", 0)) if current.get("gust_kph") else None,
                    precip_mm=float(current.get("precip_mm", 0)),
                    vis_km=float(current.get("vis_km", 10)),
                    humidity=int(current.get("humidity", 50)),
                    pressure_mb=float(current.get("pressure_mb", 0)) if current.get("pressure_mb") else None,
                    uv=float(current.get("uv", 0)) if current.get("uv") is not None else None,
                    is_historical=False,
                )
        elif is_past:
            hist_data = await get_historical_weather(waypoint_city, target_date_str)
            if hist_data:
                weather_snap = _extract_day_weather_from_history(
                    hist_data, target_date_str, day_number, location_label, city_used,
                )
        else:
            # Try route-specific forecast first, then supplier/oem fallback
            forecast_data = route_city_forecasts.get(waypoint_city)
            if not forecast_data:
                midpoint = transit_days // 2
                forecast_data = supplier_forecast if i < midpoint else oem_forecast
            if forecast_data:
                weather_snap = _extract_day_weather_from_forecast(
                    forecast_data, target_date_str, day_number, location_label, city_used,
                )
            # Fresh fetch only when city is truly missing from our pre-fetched cache
            if not weather_snap and waypoint_city not in route_city_forecasts:
                fresh_forecast = await get_forecast(waypoint_city, days=14)
                if fresh_forecast:
                    route_city_forecasts[waypoint_city] = fresh_forecast  # cache it
                    forecast_data = fresh_forecast
                    weather_snap = _extract_day_weather_from_forecast(
                        fresh_forecast, target_date_str, day_number, location_label, city_used,
                    )
            # Last resort: date is beyond 14-day API window — use last available day as estimate
            if not weather_snap and forecast_data:
                logger.info(
                    "[WeatherGraph] Day %d (%s) beyond forecast window — "
                    "using last available forecast day for %s",
                    day_number, target_date_str, city_used,
                )
                weather_snap = _get_last_forecast_day(
                    forecast_data, day_number, location_label, city_used, target_date_str,
                )

        if not weather_snap:
            logger.warning(
                "[WeatherGraph] No weather data for day %d (%s) at %s — skipping",
                day_number, target_date_str, city_used,
            )
            continue

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
                "is_estimated": d.weather.is_estimated,
                "weather": {
                    "condition": d.weather.condition,
                    "condition_code": d.weather.condition_code,
                    "temp_c": d.weather.temp_c,
                    "feelslike_c": d.weather.feelslike_c,
                    "wind_kph": d.weather.wind_kph,
                    "gust_kph": d.weather.gust_kph,
                    "precip_mm": d.weather.precip_mm,
                    "snow_cm": d.weather.snow_cm,
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
        "[WeatherGraph] Timeline built: %d days, exposure_score=%.1f, high_risk_days=%d",
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

async def _build_exposure_risks_node(state: WeatherState) -> WeatherState:
    """
    Convert the exposure payload into structured risk and opportunity dicts
    ready for DB persistence.
    """
    payload = state.get("exposure_payload") or {}

    if not payload.get("daily_timeline"):
        logger.info("[WeatherGraph] No timeline data — skipping risk/opportunity generation")
        return {"weather_risks": [], "weather_opportunities": []}

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

    # Determine severity from exposure score — use higher thresholds so that
    # moderate weather along a route does not inflate overall supplier risk.
    if exposure_score >= 80:
        severity = "critical"
    elif exposure_score >= 60:
        severity = "high"
    elif exposure_score >= 35:
        severity = "moderate"
    else:
        severity = "low"

    # Identify the dominant risk factor for precise descriptions
    factor_max = payload.get("risk_factors_max") or {}
    top_factor = max(factor_max, key=factor_max.get, default="transportation") if factor_max else "transportation"
    top_factor_score = factor_max.get(top_factor, 0)

    # Count estimated days for data quality context
    estimated_day_count = sum(
        1 for d in (payload.get("daily_timeline") or []) if d.get("is_estimated")
    )

    if exposure_score > 25:
        concern_text = "; ".join(concerns[:3]) if concerns else "Weather exposure along transit route"
        action_text = "; ".join(actions[:3]) if actions else "Monitor weather conditions"

        # Build precise description with dominant factor context
        desc_parts = [
            f"Shipment route {supplier_city} → {oem_city}: overall weather exposure "
            f"score {exposure_score:.0f}/100 ({severity}).",
        ]
        if peak_day and peak_date:
            desc_parts.append(
                f"Peak risk {peak_score:.0f}/100 on Day {peak_day} ({peak_date})."
            )
        if high_risk_count:
            desc_parts.append(f"{high_risk_count} high/critical risk day(s).")
        if top_factor_score >= 25:
            factor_label = top_factor.replace("_", " ").title()
            desc_parts.append(
                f"Dominant factor: {factor_label} (peak score {top_factor_score:.0f})."
            )
        desc_parts.append(f"Key concerns: {concern_text}.")
        if estimated_day_count:
            desc_parts.append(
                f"Note: {estimated_day_count} day(s) use projected data beyond forecast window."
            )

        risks.append({
            "title": f"Weather exposure: {supplier_city} → {oem_city} route ({severity})",
            "description": " ".join(desc_parts),
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
                    "peak_risk_date": peak_date,
                    "high_risk_day_count": high_risk_count,
                    "estimated_day_count": estimated_day_count,
                    "dominant_risk_factor": top_factor,
                    "dominant_risk_factor_score": top_factor_score,
                    "route": f"{supplier_city} -> {oem_city}",
                },
                "risk_factors_max": factor_max,
            },
        })

        # Add per-day risks only for critical days to avoid inflating the score
        # with many moderate weather entries that don't directly disrupt the supplier.
        for day_entry in (payload.get("daily_timeline") or []):
            day_score = day_entry.get("risk_score", 0)
            day_level = day_entry.get("risk_level", "low")
            if isinstance(day_level, RiskLevel):
                day_level = day_level.value
            if day_level == "critical":
                w = day_entry.get("weather", {})
                day_sev = "critical" if day_score >= 75 else "high"

                # Build detailed weather description
                weather_details = [f"{w.get('condition', 'Unknown')}"]
                weather_details.append(f"temp {w.get('temp_c', 0):.1f}°C")
                wind = w.get("wind_kph", 0)
                gust = w.get("gust_kph")
                if gust and gust > wind:
                    weather_details.append(f"wind {wind:.0f} km/h (gusts {gust:.0f})")
                else:
                    weather_details.append(f"wind {wind:.0f} km/h")
                if w.get("precip_mm", 0) > 0:
                    weather_details.append(f"precip {w['precip_mm']:.1f} mm")
                if w.get("snow_cm", 0) > 0:
                    weather_details.append(f"snow {w['snow_cm']:.1f} cm")
                if w.get("vis_km", 10) < 5:
                    weather_details.append(f"visibility {w['vis_km']:.1f} km")

                estimated_tag = " [PROJECTED]" if day_entry.get("is_estimated") else ""

                risks.append({
                    "title": f"Day {day_entry['day']} ({day_entry['date']}): {day_sev} weather risk at {day_entry['location']}",
                    "description": (
                        f"Weather at {day_entry['location']}: {', '.join(weather_details)}. "
                        f"Risk score: {day_score:.0f}/100. "
                        f"{day_entry.get('key_concern', '')}{estimated_tag}"
                    ),
                    "severity": day_sev,
                    "affectedRegion": day_entry["location"],
                    "affectedSupplier": supplier_name,
                    "estimatedImpact": (
                        f"Transit disruption likely on Day {day_entry['day']} — "
                        f"{day_entry.get('key_concern', 'adverse weather conditions')}"
                    ),
                    "estimatedCost": None,
                    "sourceType": "weather",
                    "sourceData": {
                        "weatherExposure": {
                            "weather_exposure_score": day_score,
                            "day_number": day_entry["day"],
                            "date": day_entry["date"],
                            "location": day_entry["location"],
                            "is_estimated": day_entry.get("is_estimated", False),
                            "weather_snapshot": w,
                        },
                    },
                })
    else:
        # Favorable conditions — provide actionable opportunity
        timeline = payload.get("daily_timeline") or []
        avg_temp = sum(d["weather"]["temp_c"] for d in timeline) / len(timeline) if timeline else 0
        max_wind = max((d["weather"]["wind_kph"] for d in timeline), default=0) if timeline else 0

        opportunities.append({
            "title": f"Favorable weather: {supplier_city} → {oem_city} route clear",
            "description": (
                f"Weather conditions along the {supplier_city} → {oem_city} "
                f"transit route are stable with exposure score {exposure_score:.0f}/100. "
                f"Average temperature {avg_temp:.1f}°C, max wind {max_wind:.0f} km/h. "
                f"No high-risk days identified across the {state.get('transit_days', 0)}-day transit window."
            ),
            "type": "time_saving",
            "affectedRegion": f"{supplier_city} - {oem_city}",
            "potentialBenefit": (
                "Conditions favor on-time or expedited delivery. "
                "Consider prioritizing high-value or time-sensitive shipments on this route."
            ),
            "estimatedValue": None,
            "sourceType": "weather",
            "sourceData": {
                "weatherExposure": {
                    "weather_exposure_score": exposure_score,
                    "route": f"{supplier_city} -> {oem_city}",
                    "avg_temp_c": round(avg_temp, 1),
                    "max_wind_kph": round(max_wind, 1),
                },
            },
        })

    logger.info(
        "[WeatherGraph] Exposure risks built: risks=%d opportunities=%d",
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
        (
            "You are a senior supply chain weather risk analyst writing production-grade "
            "executive briefings for logistics operations teams. Your job is to TRANSLATE "
            "pre-computed risk data into clear, precise, actionable prose. You NEVER "
            "re-score, invent, exaggerate, or downplay risks.\n\n"
            "STRICT ACCURACY RULES (violation = operational harm):\n"
            "1. Every claim MUST cite exact numbers from the data: day numbers, dates, "
            "scores, city names, weather values (temp, wind, precip). No rounding unless "
            "the data is already rounded.\n"
            "2. Do NOT speculate, hypothesize, or add information not present in the data. "
            "No generic supply chain advice. No 'could potentially' language.\n"
            "3. If overall_exposure_score < 35 AND high_risk_day_count is 0, state that "
            "conditions are favorable for transit — do NOT manufacture or imply risks.\n"
            "4. Mitigations MUST map to the specific risk factors that scored highest in "
            "risk_factors_max (transportation, port_and_route, power_outage, production, "
            "raw_material_delay). Never suggest mitigations for factors scoring below 25.\n"
            "5. Never fabricate weather events, cost figures, delay estimates, or disruption "
            "timelines that are not directly stated in the data.\n"
            "6. If any day has is_estimated=true, explicitly note that those days use "
            "projected data beyond the 14-day forecast window and carry lower confidence.\n"
            "7. Severity language must match scores exactly:\n"
            "   - Score <35: 'low risk' or 'favorable'\n"
            "   - Score 35-59: 'moderate risk'\n"
            "   - Score 60-79: 'high risk' — use urgent but measured language\n"
            "   - Score >=80: 'critical risk' — flag for immediate operational attention\n"
            "8. When transport_mode is available (sea, air, road, rail), tailor risk "
            "interpretation: sea freight is sensitive to wind/waves, air to visibility/storms, "
            "road to precipitation/ice, rail to extreme temperature.\n"
            "9. Do NOT use phrases like 'I recommend' or 'In my assessment'. Write as an "
            "objective risk report."
        ),
    ),
    (
        "user",
        (
            "SHIPMENT ROUTE: {supplier_city} → {oem_city}\n"
            "TRANSIT: {transit_days} days starting {start_date}\n\n"
            "PRE-COMPUTED RISK DATA (narrate these numbers verbatim — do not re-derive or reinterpret):\n"
            "{exposure_json}\n\n"
            "Write a 3–5 sentence executive briefing following this exact structure:\n"
            "1. OPEN: State the overall_exposure_score, its severity band, and the route.\n"
            "2. PEAK: Name the peak-risk day number, its exact date, location, weather "
            "condition, and score. If high_risk_day_count > 1, state the total count.\n"
            "3. DRIVERS: Name the top 1-2 risk factors from risk_factors_max with their "
            "peak scores and the specific weather conditions driving them (wind speed, "
            "precip amount, visibility, condition name).\n"
            "4. ACTION: 2-3 specific mitigations that directly address the identified "
            "drivers. If score <25, state that no mitigations are needed and conditions "
            "favor expedited shipping.\n\n"
            "Format: Plain professional prose. Exact numbers from the data. No bullet points. "
            "No markdown. Under 600 characters."
        ),
    ),
])


async def _llm_summary_node(state: WeatherState) -> WeatherState:
    """Generate an optional LLM executive summary for the weather exposure."""
    payload = state.get("exposure_payload") or {}
    supplier_city = state.get("supplier_city", "Unknown")
    oem_city = state.get("oem_city", "Unknown")
    transit_days = state.get("transit_days", DEFAULT_TRANSIT_DAYS)
    start_date = state.get("shipment_start_date", "")
    oem_name = state.get("oem_name")
    supplier_name = state.get("supplier_name")

    import json
    # Include daily timeline + risk factors so LLM can reference specific days accurately
    timeline_brief = [
        {
            "day": d["day"], "date": d["date"], "location": d["location"],
            "condition": d["weather"]["condition"],
            "temp_c": d["weather"]["temp_c"], "wind_kph": d["weather"]["wind_kph"],
            "precip_mm": d["weather"]["precip_mm"],
            "snow_cm": d["weather"].get("snow_cm", 0),
            "vis_km": d["weather"].get("vis_km", 10),
            "humidity": d["weather"].get("humidity", 50),
            "risk_score": d["risk_score"], "risk_level": d["risk_level"],
            "key_concern": d.get("key_concern", ""),
            "is_estimated": d.get("is_estimated", False),
            "is_historical": d.get("is_historical", False),
        }
        for d in (payload.get("daily_timeline") or [])
    ]
    exposure_data = {
        **(payload.get("exposure_summary") or {}),
        "risk_factors_max": payload.get("risk_factors_max", {}),
        "primary_concerns": (payload.get("primary_concerns") or [])[:4],
        "recommended_actions": (payload.get("recommended_actions") or [])[:4],
        "daily_timeline": timeline_brief,
    }
    exposure_json = json.dumps(exposure_data, indent=2)

    llm = get_chat_model()
    if not llm:
        logger.info("[WeatherGraph] LLM unavailable — no summary generated")
        return {"agent_summary": None}

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
            f"Generating weather risk summary",
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
            "[WeatherGraph] LLM summary id=%s provider=%s elapsed_ms=%d len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, raw_text, "success", elapsed, None,
        )

        summary = raw_text.strip() or None

        await _broadcast_progress(
            "llm_summary_done",
            "Weather risk summary generated",
            {"elapsed_ms": elapsed},
            oem_name=oem_name, supplier_name=supplier_name,
        )

        return {"agent_summary": summary}

    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[WeatherGraph] LLM summary error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, None, "error", elapsed, str(exc),
        )
        await _broadcast_progress(
            "llm_summary_error", f"LLM summary failed: {exc}",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"agent_summary": None}


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(WeatherState)

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

WEATHER_GRAPH = _builder.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def run_weather_graph(
    scope: OemScope,
) -> dict[str, list[dict]]:
    """
    Orchestrate the Weather Exposure Agent using LangGraph.

    Resolves supplier/OEM cities from scope, fetches weather forecasts,
    builds a day-by-day risk timeline, and produces structured risks
    and opportunities ready for DB persistence.

    Returns ``{"risks": [...], "opportunities": [...]}``
    """
    oem_label = scope.get("oemName") or "unknown"
    supplier_label = scope.get("supplierName") or "unknown"
    entity_label = f"{oem_label}/{supplier_label}"

    logger.info("[WeatherGraph] Starting for %s", entity_label)
    await _broadcast_progress(
        "started",
        f"Starting weather analysis for {entity_label}",
        {"oem": oem_label, "supplier": supplier_label},
        oem_name=oem_label, supplier_name=supplier_label,
    )

    initial_state: WeatherState = {
        "scope": scope,
    }

    final_state = await WEATHER_GRAPH.ainvoke(initial_state)

    risks = final_state.get("weather_risks") or []
    opps = final_state.get("weather_opportunities") or []
    daily_timeline = final_state.get("day_results") or []

    oem_resolved = final_state.get("oem_name") or oem_label
    supplier_resolved = final_state.get("supplier_name") or supplier_label
    logger.info(
        "[WeatherGraph] Completed: oem=%r supplier=%r risks=%d opportunities=%d daily_days=%d",
        oem_resolved, supplier_resolved, len(risks), len(opps), len(daily_timeline),
    )
    await _broadcast_progress(
        "agent_done",
        f"Weather analysis complete: {len(risks)} risks, {len(opps)} opportunities, {len(daily_timeline)} days",
        {"risks": len(risks), "opportunities": len(opps), "daily_days": len(daily_timeline)},
        oem_name=oem_resolved, supplier_name=supplier_resolved,
    )

    return {
        "risks": risks,
        "opportunities": opps,
        "daily_timeline": daily_timeline,
        "exposure_payload": final_state.get("exposure_payload"),
        "supplier_city": final_state.get("supplier_city"),
        "oem_city": final_state.get("oem_city"),
        "route_plan": final_state.get("route_plan"),
        "agent_summary": final_state.get("agent_summary"),
    }


# ---------------------------------------------------------------------------
# Backward-compat: run_weather_agent (used by REST API route)
# ---------------------------------------------------------------------------

async def run_weather_agent(
    supplier_city: str,
    oem_city: str,
    shipment_start_date: str,
    transit_days: int,
) -> "ShipmentWeatherExposureResponse":
    """
    Backward-compatible wrapper for the ``/shipment/weather-exposure`` API route.

    Builds an OemScope from the explicit parameters, invokes the graph, and
    converts the final state into a ``ShipmentWeatherExposureResponse``.
    """
    from app.schemas.weather_agent import ShipmentWeatherExposureResponse

    scope: OemScope = {
        "oemId": "",
        "oemName": "",
        "supplierNames": [],
        "locations": [],
        "cities": [oem_city, supplier_city],
        "countries": [],
        "regions": [],
        "commodities": [],
        "supplierId": "",
        "supplierName": "",
    }

    initial_state: WeatherState = {
        "scope": scope,
        "transit_days": transit_days,
        "shipment_start_date": shipment_start_date,
    }

    final_state = await WEATHER_GRAPH.ainvoke(initial_state)

    day_dicts = final_state.get("day_results") or []
    days = [DayRiskSnapshot(**d) for d in day_dicts]
    payload = final_state.get("exposure_payload") or {}
    summary_data = payload.get("exposure_summary") or {}

    exposure_score = summary_data.get("overall_exposure_score", 0.0)

    if exposure_score >= 80:
        overall_level = RiskLevel.CRITICAL
    elif exposure_score >= 60:
        overall_level = RiskLevel.HIGH
    elif exposure_score >= 35:
        overall_level = RiskLevel.MODERATE
    else:
        overall_level = RiskLevel.LOW

    return ShipmentWeatherExposureResponse(
        supplier_city=supplier_city,
        oem_city=oem_city,
        shipment_start_date=shipment_start_date,
        transit_days=transit_days,
        days=days,
        overall_exposure_level=overall_level,
        overall_exposure_score=exposure_score,
        risk_analysis_payload=payload,
        agent_summary=final_state.get("agent_summary"),
    )


# ---------------------------------------------------------------------------
# Backward-compat: run_weather_agent_graph (used by v1 supplier_risk_graph)
# ---------------------------------------------------------------------------

import json as _json

from app.services.agent_orchestrator import _extract_json


class _LegacyWeatherItem(TypedDict):
    city: str
    country: str
    temperature: float | int | None
    condition: str
    description: str
    humidity: int | None
    windSpeed: float | int | None
    visibility: int | None


class _LegacyWeatherState(TypedDict, total=False):
    scope: OemScope
    weather_data: dict[str, list[dict]]
    weather_items: list[_LegacyWeatherItem]
    weather_risks: list[dict]
    weather_opportunities: list[dict]


def _build_legacy_weather_items(state: _LegacyWeatherState) -> _LegacyWeatherState:
    raw = state.get("weather_data") or {}
    items = raw.get("weather") or []
    normalized: list[_LegacyWeatherItem] = []
    for item in items:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        normalized.append({
            "city": str(data.get("city") or ""),
            "country": str(data.get("country") or ""),
            "temperature": data.get("temperature"),
            "condition": str(data.get("condition") or ""),
            "description": str(data.get("description") or ""),
            "humidity": data.get("humidity"),
            "windSpeed": data.get("windSpeed"),
            "visibility": data.get("visibility"),
        })
    return {"weather_items": normalized}


_legacy_prompt: ChatPromptTemplate | None = None


def _get_legacy_chain():
    global _legacy_prompt
    llm = get_chat_model()
    if llm is None:
        return None
    if _legacy_prompt is None:
        _legacy_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are a production supply chain weather risk analyst. You receive "
                    "real-time weather observations for cities on a shipment route and produce "
                    "ONLY risks and opportunities that are directly and objectively supported "
                    "by the measured data. This output drives automated operational decisions "
                    "— accuracy is critical.\n\n"
                    "RISK CLASSIFICATION THRESHOLDS (use these exactly):\n"
                    "- Wind: >30 km/h = low risk, >50 km/h = high risk, >80 km/h = critical\n"
                    "- Precipitation: >2 mm = low risk, >10 mm = high risk, >25 mm = critical\n"
                    "- Temperature: >35°C or <-5°C = moderate risk, >40°C or <-15°C = high/critical\n"
                    "- Visibility: <5 km = low risk, <2 km = high risk, <1 km = critical\n"
                    "- Humidity >90% with temp >25°C = moderate heat-stress risk\n"
                    "- Storms/thunderstorms in condition text = high risk minimum\n"
                    "- Snow/ice/blizzard in condition text = high risk minimum for road freight\n\n"
                    "ACCURACY RULES:\n"
                    "1. Only flag a risk when measured values EXCEED the thresholds above. "
                    "Normal weather (clear skies, moderate temp, light breeze) is NOT a risk.\n"
                    "2. For mild/favorable weather, produce an opportunity — do NOT invent risks.\n"
                    "3. Severity MUST match the threshold bands above — never inflate or deflate.\n"
                    "4. Descriptions MUST quote the exact measured values from the data "
                    "(e.g., 'wind at 62 km/h', 'temperature 42°C', 'visibility 0.8 km').\n"
                    "5. estimatedCost and estimatedValue must always be null — never guess "
                    "monetary values without actual cost data.\n"
                    "6. estimatedImpact must describe the specific operational consequence "
                    "(e.g., 'road freight delays of 4-8 hours', 'port crane operations suspended', "
                    "'outdoor loading halted') — not vague language like 'may cause issues'.\n"
                    "7. affectedSupplier should be null unless you can identify it from context.\n"
                    "8. Return ONLY valid JSON. No markdown, no explanation, no code fences, "
                    "no text before or after the JSON object."
                ),
            ),
            (
                "user",
                (
                    "Analyze the weather data below for supply chain risks and opportunities.\n\n"
                    "WEATHER DATA BY CITY:\n{weather_items_json}\n\n"
                    "INSTRUCTIONS:\n"
                    "- For each city with adverse conditions exceeding the thresholds, create one risk entry.\n"
                    "- For each city with calm/favorable conditions, create one opportunity entry.\n"
                    "- Cities with unremarkable, average weather get NO entry (skip them).\n"
                    "- If ALL cities have normal weather, return empty risks array and one "
                    "combined opportunity.\n\n"
                    "Return ONLY this JSON structure:\n"
                    '{{"risks": [{{"title": "<city>: <specific condition e.g. Heavy rain warning>", '
                    '"description": "<Must quote exact values: temperature Xc, wind Y km/h, '
                    'precipitation Z mm, visibility W km, condition: text>", '
                    '"severity": "low"|"moderate"|"high"|"critical", '
                    '"affectedRegion": "<city, country>", '
                    '"affectedSupplier": null, '
                    '"estimatedImpact": "<specific operational impact with estimated delay/disruption>", '
                    '"estimatedCost": null}}], '
                    '"opportunities": [{{"title": "<city>: <favorable condition>", '
                    '"description": "<cite actual favorable values from data>", '
                    '"type": "cost_saving"|"time_saving"|"quality_improvement"|'
                    '"market_expansion"|"supplier_diversification", '
                    '"affectedRegion": "<city, country>", '
                    '"potentialBenefit": "<specific benefit: e.g. clear window for expedited shipping>", '
                    '"estimatedValue": null}}]}}'
                ),
            ),
        ])
    return _legacy_prompt | llm


async def _legacy_weather_risk_llm(state: _LegacyWeatherState) -> _LegacyWeatherState:
    items = state.get("weather_items") or []
    if not items:
        return {"weather_risks": [], "weather_opportunities": []}
    chain = _get_legacy_chain()
    if not chain:
        return {"weather_risks": [], "weather_opportunities": []}
    try:
        items_json = _json.dumps(items, indent=2)
        msg = await chain.ainvoke({"weather_items_json": items_json})
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
        parsed = _extract_json(raw_text) or {}
        risks = [r for r in (parsed.get("risks") or []) if isinstance(r, dict) and r.get("title") and r.get("description")]
        opps = [o for o in (parsed.get("opportunities") or []) if isinstance(o, dict) and o.get("title") and o.get("description")]
        return {"weather_risks": risks, "weather_opportunities": opps}
    except Exception as exc:
        logger.exception("Legacy WeatherAgent LLM error: %s", exc)
        return {"weather_risks": [], "weather_opportunities": []}


_legacy_builder = StateGraph(_LegacyWeatherState)
_legacy_builder.add_node("build_items", _build_legacy_weather_items)
_legacy_builder.add_node("weather_risk_llm", _legacy_weather_risk_llm)
_legacy_builder.set_entry_point("build_items")
_legacy_builder.add_edge("build_items", "weather_risk_llm")
_legacy_builder.add_edge("weather_risk_llm", END)
_LEGACY_WEATHER_GRAPH = _legacy_builder.compile()


async def run_weather_agent_graph(
    weather_data: dict[str, list[dict]],
    scope: OemScope,
) -> dict[str, list[dict]]:
    """
    Legacy v1 weather agent — takes pre-fetched weather data and runs
    LLM risk extraction.  Used by ``supplier_risk_graph`` and
    ``agent_service._run_analysis_for_oem``.
    """
    initial_state: _LegacyWeatherState = {
        "scope": scope,
        "weather_data": weather_data,
    }
    final_state = await _LEGACY_WEATHER_GRAPH.ainvoke(initial_state)

    risks = final_state.get("weather_risks") or []
    opps = final_state.get("weather_opportunities") or []

    risks_for_db: list[dict] = []
    opps_for_db: list[dict] = []

    for r in risks:
        risks_for_db.append({
            "title": r["title"],
            "description": r["description"],
            "severity": r.get("severity"),
            "affectedRegion": r.get("affectedRegion"),
            "affectedSupplier": r.get("affectedSupplier"),
            "estimatedImpact": r.get("estimatedImpact"),
            "estimatedCost": r.get("estimatedCost"),
            "sourceType": "weather",
            "sourceData": {
                "weatherExposure": {
                    "weather_exposure_score": r.get("weather_exposure_score"),
                    "storm_risk": r.get("storm_risk"),
                    "temperature_extreme_days": r.get("temperature_extreme_days"),
                }
            },
        })

    for o in opps:
        opps_for_db.append({
            "title": o["title"],
            "description": o["description"],
            "type": o.get("type"),
            "affectedRegion": o.get("affectedRegion"),
            "potentialBenefit": o.get("potentialBenefit"),
            "estimatedValue": o.get("estimatedValue"),
            "sourceType": "weather",
            "sourceData": None,
        })

    return {
        "risks": risks_for_db,
        "opportunities": opps_for_db,
        "weather_items": final_state.get("weather_items") or [],
    }
