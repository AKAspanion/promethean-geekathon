from __future__ import annotations

from typing import Any

from app.schemas.weather_agent import RiskFactor, RiskLevel


def _level_from_score(score: float) -> RiskLevel:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _clamp_score(v: float) -> float:
    return min(100.0, max(0.0, float(v)))


def _transportation_risk(current: dict[str, Any]) -> RiskFactor:
    wind_kph = float(current.get("wind_kph") or 0)
    gust_kph = float(current.get("gust_kph") or wind_kph)
    precip_mm = float(current.get("precip_mm") or 0)
    vis_km = float(current.get("vis_km") or 10)
    condition = current.get("condition") or {}
    code = int(condition.get("code", 1000))
    is_snow_ice = code in (
        1063,
        1066,
        1069,
        1072,
        1210,
        1213,
        1216,
        1219,
        1222,
        1225,
        1237,
        1255,
        1261,
        1264,
    )

    score = 0.0
    reasons: list[str] = []
    if wind_kph > 50 or gust_kph > 70:
        score += 45
        reasons.append("High wind: truck speed reductions and possible route closures")
    elif wind_kph > 30 or gust_kph > 50:
        score += 25
        reasons.append("Moderate wind may slow road freight")
    if precip_mm > 10:
        score += 30
        reasons.append("Heavy precipitation: road delays and visibility issues")
    elif precip_mm > 2:
        score += 15
        reasons.append("Rain may cause minor delays")
    if vis_km < 1:
        score += 35
        reasons.append("Very low visibility: unsafe for road transport")
    elif vis_km < 5:
        score += 20
        reasons.append("Reduced visibility may slow logistics")
    if is_snow_ice:
        score += 40
        reasons.append("Snow/ice: significant transport disruption risk")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons)
        if reasons
        else "No significant transport risk from current weather."
    )
    mitigation = None
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        mitigation = "Consider alternate routes, delay non-urgent shipments, and confirm port/road status before dispatch."
    return RiskFactor(
        factor="transportation",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind {wind_kph} km/h (gusts {gust_kph}), precip {precip_mm} mm, visibility {vis_km} km.",
        mitigation=mitigation,
    )


def _power_outage_risk(current: dict[str, Any]) -> RiskFactor:
    wind_kph = float(current.get("wind_kph") or 0)
    gust_kph = float(current.get("gust_kph") or wind_kph)
    precip_mm = float(current.get("precip_mm") or 0)
    condition = current.get("condition") or {}
    code = int(condition.get("code", 1000))
    is_storm = code in (1087, 1273, 1276, 1279, 1282) or 2000 <= code <= 2300

    score = 0.0
    reasons: list[str] = []
    if is_storm:
        score += 50
        reasons.append("Thunderstorms increase power outage and equipment damage risk")
    if gust_kph > 60:
        score += 35
        reasons.append("Strong gusts can cause line damage and outages")
    elif wind_kph > 40:
        score += 20
        reasons.append("High wind may affect power infrastructure")
    if precip_mm > 15:
        score += 15
        reasons.append("Heavy rain can cause local flooding and substation issues")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons) if reasons else "Low power outage risk from current weather."
    )
    mitigation = None
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        mitigation = "Prepare backup power and prioritize critical loads; coordinate with local utility for outage alerts."
    return RiskFactor(
        factor="power_outage",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind gusts {gust_kph} km/h, precip {precip_mm} mm, storm-related codes considered.",
        mitigation=mitigation,
    )


def _production_risk(current: dict[str, Any]) -> RiskFactor:
    temp_c = float(current.get("temp_c") or 20)
    feelslike_c = float(current.get("feelslike_c") or temp_c)
    humidity = int(current.get("humidity") or 50)
    uv = current.get("uv")
    uv_val = float(uv) if uv is not None else 5.0

    score = 0.0
    reasons: list[str] = []
    if feelslike_c >= 40:
        score += 45
        reasons.append("Extreme heat: worker safety and cooling load stress")
    elif feelslike_c >= 35:
        score += 25
        reasons.append("High heat may reduce productivity and require extra cooling")
    elif feelslike_c <= -15:
        score += 40
        reasons.append("Extreme cold: heating and workforce safety")
    elif feelslike_c <= -5:
        score += 20
        reasons.append("Cold conditions may affect outdoor work and logistics")
    if humidity >= 90 and temp_c > 25:
        score += 20
        reasons.append("High humidity with heat increases heat-stress risk")
    if uv_val >= 10:
        score += 15
        reasons.append("Very high UV: limit prolonged outdoor exposure")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons) if reasons else "Weather within normal range for production."
    )
    mitigation = None
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        mitigation = "Adjust shifts for extreme temps, ensure HVAC and PPE; plan for higher energy demand or heating needs."
    return RiskFactor(
        factor="production",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Temp {temp_c}°C (feels like {feelslike_c}°C), humidity {humidity}%, UV index {uv_val}.",
        mitigation=mitigation,
    )


def _port_and_route_risk(current: dict[str, Any]) -> RiskFactor:
    wind_kph = float(current.get("wind_kph") or 0)
    gust_kph = float(current.get("gust_kph") or wind_kph)
    precip_mm = float(current.get("precip_mm") or 0)
    vis_km = float(current.get("vis_km") or 10)
    condition = current.get("condition") or {}
    code = int(condition.get("code", 1000))

    score = 0.0
    reasons: list[str] = []
    if gust_kph > 80:
        score += 55
        reasons.append("Very high winds: port operations and flights likely disrupted")
    elif gust_kph > 55:
        score += 35
        reasons.append("Strong winds may delay port and airport operations")
    elif wind_kph > 40:
        score += 20
        reasons.append("Elevated wind may cause delays at ports and airports")
    if precip_mm > 20:
        score += 25
        reasons.append("Heavy precipitation can cause port/runway delays")
    if vis_km < 2:
        score += 25
        reasons.append("Low visibility impacts maritime and aviation operations")
    if code in (1195, 1198, 1201, 1204, 1207, 1210, 1213, 1216, 1219, 1222, 1225):
        score += 40
        reasons.append("Severe storm conditions: high port/route closure probability")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons) if reasons else "No significant port or route closure risk."
    )
    mitigation = None
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        mitigation = "Check port/airport advisories; plan for 3-5 day backlog and alternative routing or modes."
    return RiskFactor(
        factor="port_and_route",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind {wind_kph} km/h (gusts {gust_kph}), precip {precip_mm} mm, visibility {vis_km} km.",
        mitigation=mitigation,
    )


def _raw_material_delay_risk(current: dict[str, Any]) -> RiskFactor:
    trans = _transportation_risk(current)
    port = _port_and_route_risk(current)
    combined = _clamp_score((trans.score + port.score) / 2.0 * 1.1)
    level = _level_from_score(combined)
    return RiskFactor(
        factor="raw_material_delay",
        level=level,
        score=round(combined, 1),
        summary=f"Raw material delay risk from logistics: {trans.summary}",
        details=f"Derived from transportation ({trans.score}) and port/route ({port.score}) risk.",
        mitigation=trans.mitigation or port.mitigation,
    )


def compute_risk(current_weather: dict[str, Any]) -> dict[str, Any]:
    current = current_weather.get("current") or current_weather
    if not current:
        return {
            "overall_level": RiskLevel.LOW,
            "overall_score": 0.0,
            "factors": [],
            "primary_concerns": ["No weather data available."],
            "suggested_actions": ["Obtain current weather data for risk assessment."],
        }

    factors = [
        _transportation_risk(current),
        _power_outage_risk(current),
        _production_risk(current),
        _port_and_route_risk(current),
        _raw_material_delay_risk(current),
    ]
    scores = [f.score for f in factors]
    overall_score = min(100.0, (max(scores) * 0.5 + (sum(scores) / len(scores)) * 0.5))
    overall_level = _level_from_score(overall_score)
    primary_concerns = [
        f.summary for f in factors if f.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    ]
    if not primary_concerns:
        primary_concerns = [
            "No high or critical risks identified for current conditions."
        ]
    suggested_actions = list(
        dict.fromkeys([f.mitigation for f in factors if f.mitigation])
    )

    return {
        "overall_level": overall_level,
        "overall_score": round(overall_score, 1),
        "factors": factors,
        "primary_concerns": primary_concerns,
        "suggested_actions": suggested_actions,
    }
