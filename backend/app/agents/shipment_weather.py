"""
Shipment Weather Exposure Agent
- Takes: supplier_city, oem_city, shipment_start_date, transit_days
- Builds a day-by-day timeline with estimated location along the route
- Day 1: current weather + forecast for remaining days
- Day 2+: uses historical API for past days, forecast for future days
- Computes per-day risk and structures a Risk Analysis Agent payload
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.config import settings
from app.core.risk_engine import compute_risk
from app.schemas.weather_agent import (
    DayRiskSnapshot,
    DayWeatherSnapshot,
    RiskLevel,
    RiskSummary,
    ShipmentWeatherExposureResponse,
)
from app.services.weather_service import (
    get_current_weather,
    get_forecast,
    get_historical_weather,
)

logger = logging.getLogger(__name__)


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


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _extract_day_weather_from_forecast(
    forecast_data: dict[str, Any],
    target_date: str,
    day_number: int,
    location_label: str,
    city_used: str,
) -> DayWeatherSnapshot | None:
    try:
        forecast_days = forecast_data.get("forecast", {}).get("forecastday", [])
        for fd in forecast_days:
            if fd.get("date") == target_date:
                day = fd.get("day", {})
                cond = day.get("condition", {})
                return DayWeatherSnapshot(
                    date=target_date,
                    day_number=day_number,
                    location_name=location_label,
                    estimated_location=city_used,
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
    hist_data: dict[str, Any],
    target_date: str,
    day_number: int,
    location_label: str,
    city_used: str,
) -> DayWeatherSnapshot | None:
    try:
        forecast_days = hist_data.get("forecast", {}).get("forecastday", [])
        for fd in forecast_days:
            if fd.get("date") == target_date:
                day = fd.get("day", {})
                cond = day.get("condition", {})
                return DayWeatherSnapshot(
                    date=target_date,
                    day_number=day_number,
                    location_name=location_label,
                    estimated_location=city_used,
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


def _weather_snapshot_to_current_dict(snap: DayWeatherSnapshot) -> dict[str, Any]:
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


def _build_risk_analysis_payload(
    supplier_city: str,
    oem_city: str,
    shipment_start_date: str,
    transit_days: int,
    days: list[DayRiskSnapshot],
) -> dict[str, Any]:
    peak_risk_day = max(days, key=lambda d: d.risk.overall_score) if days else None
    avg_score = sum(d.risk.overall_score for d in days) / len(days) if days else 0

    high_risk_days = [
        d for d in days if d.risk.overall_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    ]

    all_concerns: list[str] = []
    all_actions: list[str] = []
    for d in days:
        all_concerns.extend(d.risk.primary_concerns)
        all_actions.extend(d.risk.suggested_actions)

    unique_concerns = list(dict.fromkeys(all_concerns))
    unique_actions = list(dict.fromkeys(all_actions))

    factor_names = [
        "transportation",
        "power_outage",
        "production",
        "port_and_route",
        "raw_material_delay",
    ]
    factor_max_scores: dict[str, float] = {f: 0.0 for f in factor_names}
    for d in days:
        for factor in d.risk.factors:
            fn = factor.factor
            if fn in factor_max_scores:
                factor_max_scores[fn] = max(factor_max_scores[fn], factor.score)

    return {
        "shipment_metadata": {
            "supplier_city": supplier_city,
            "oem_city": oem_city,
            "start_date": shipment_start_date,
            "transit_days": transit_days,
        },
        "exposure_summary": {
            "average_risk_score": round(avg_score, 1),
            "peak_risk_score": round(peak_risk_day.risk.overall_score, 1)
            if peak_risk_day
            else 0,
            "peak_risk_day": peak_risk_day.day_number if peak_risk_day else None,
            "peak_risk_date": peak_risk_day.date if peak_risk_day else None,
            "high_risk_day_count": len(high_risk_days),
            "high_risk_dates": [d.date for d in high_risk_days],
        },
        "risk_factors_max": factor_max_scores,
        "primary_concerns": unique_concerns[:6],
        "recommended_actions": unique_actions[:6],
        "daily_timeline": [
            {
                "day": d.day_number,
                "date": d.date,
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
                "key_concern": d.risk.primary_concerns[0]
                if d.risk.primary_concerns
                else "No significant risk",
            }
            for d in days
        ],
    }


async def run_shipment_weather_agent(
    supplier_city: str,
    oem_city: str,
    shipment_start_date: str,
    transit_days: int,
) -> ShipmentWeatherExposureResponse:
    today = date.today()
    start_date = _parse_date(shipment_start_date)

    waypoints = _interpolate_waypoints(supplier_city, oem_city, transit_days)

    forecast_days_needed = max(
        0, (start_date + timedelta(days=transit_days - 1) - today).days + 1
    )
    forecast_days_needed = min(forecast_days_needed + 1, 14)

    supplier_forecast, oem_forecast = await asyncio.gather(
        get_forecast(supplier_city, days=forecast_days_needed),
        get_forecast(oem_city, days=forecast_days_needed),
    )

    day_results: list[DayRiskSnapshot] = []

    for i, waypoint_city in enumerate(waypoints):
        day_number = i + 1
        target_date = start_date + timedelta(days=i)
        target_date_str = target_date.strftime("%Y-%m-%d")

        is_past = target_date < today
        is_today = target_date == today

        location_label = (
            f"{supplier_city} (Origin)"
            if i == 0
            else f"{oem_city} (Destination)"
            if i == transit_days - 1
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
                    date=target_date_str,
                    day_number=day_number,
                    location_name=location_label,
                    estimated_location=city_used,
                    condition=cond.get("text", "Unknown"),
                    temp_c=float(current.get("temp_c", 0)),
                    min_temp_c=None,
                    max_temp_c=None,
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
                    hist_data, target_date_str, day_number, location_label, city_used
                )

        else:
            midpoint = transit_days // 2
            forecast_data = supplier_forecast if i < midpoint else oem_forecast
            if forecast_data:
                weather_snap = _extract_day_weather_from_forecast(
                    forecast_data,
                    target_date_str,
                    day_number,
                    location_label,
                    city_used,
                )
            if not weather_snap:
                fresh_forecast = await get_forecast(waypoint_city, days=14)
                if fresh_forecast:
                    weather_snap = _extract_day_weather_from_forecast(
                        fresh_forecast,
                        target_date_str,
                        day_number,
                        location_label,
                        city_used,
                    )

        if not weather_snap:
            weather_snap = DayWeatherSnapshot(
                date=target_date_str,
                day_number=day_number,
                location_name=location_label,
                estimated_location=city_used,
                condition="Data unavailable",
                temp_c=25.0,
                min_temp_c=None,
                max_temp_c=None,
                wind_kph=10.0,
                precip_mm=0.0,
                vis_km=10.0,
                humidity=50,
                is_historical=is_past,
            )

        current_dict = _weather_snapshot_to_current_dict(weather_snap)
        risk_raw = compute_risk({"current": current_dict})
        factors_serialized = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in risk_raw.get("factors", [])
        ]
        risk_dict_serialized = {**risk_raw, "factors": factors_serialized}
        if hasattr(risk_dict_serialized.get("overall_level"), "value"):
            risk_dict_serialized["overall_level"] = risk_dict_serialized[
                "overall_level"
            ].value
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
            f"{weather_snap.condition}, {weather_snap.temp_c:.1f}°C, wind {weather_snap.wind_kph:.0f} km/h. "
            f"Risk: {risk_summary.overall_level} ({risk_summary.overall_score:.0f}/100). {concern_text}"
        )

        day_results.append(
            DayRiskSnapshot(
                date=target_date_str,
                day_number=day_number,
                location_name=location_label,
                weather=weather_snap,
                risk=risk_summary,
                risk_summary_text=risk_summary_text,
            )
        )

    all_scores = [d.risk.overall_score for d in day_results]
    if all_scores:
        avg_score = sum(all_scores) / len(all_scores)
        max_score = max(all_scores)
        exposure_score = round(max_score * 0.5 + avg_score * 0.5, 1)
    else:
        exposure_score = 0.0

    def _level_from_score(s: float) -> RiskLevel:
        if s >= 75:
            return RiskLevel.CRITICAL
        if s >= 50:
            return RiskLevel.HIGH
        if s >= 25:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    overall_level = _level_from_score(exposure_score)

    risk_analysis_payload = _build_risk_analysis_payload(
        supplier_city, oem_city, shipment_start_date, transit_days, day_results
    )

    agent_summary: str | None = None
    try:
        from langchain_core.messages import HumanMessage
        from langchain_ollama import ChatOllama

        timeline_text = "\n".join(d.risk_summary_text for d in day_results)
        peak = risk_analysis_payload["exposure_summary"]
        prompt = (
            f"You are a supply chain risk analyst. A shipment is travelling from {supplier_city} to {oem_city} "
            f"over {transit_days} days starting {shipment_start_date}.\n\n"
            f"Day-by-day weather risk timeline:\n{timeline_text}\n\n"
            f"Overall exposure score: {exposure_score}/100 ({overall_level}). "
            f"Peak risk on Day {peak['peak_risk_day']} ({peak['peak_risk_date']}, score {peak['peak_risk_score']}/100). "
            f"{peak['high_risk_day_count']} high/critical risk days identified.\n\n"
            f"Write a concise executive summary (3-5 sentences) for an OEM operations manager: "
            f"highlight the worst weather windows, which days/legs are most exposed, and top 2-3 mitigation actions."
        )
        llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.3,
            num_predict=500,
        )
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        agent_summary = (
            resp.content if hasattr(resp, "content") else str(resp)
        ).strip() or None
    except Exception as e:
        logger.warning("LLM summary failed (non-fatal): %s", e)

    return ShipmentWeatherExposureResponse(
        supplier_city=supplier_city,
        oem_city=oem_city,
        shipment_start_date=shipment_start_date,
        transit_days=transit_days,
        days=day_results,
        overall_exposure_level=overall_level,
        overall_exposure_score=exposure_score,
        risk_analysis_payload=risk_analysis_payload,
        agent_summary=agent_summary,
    )
