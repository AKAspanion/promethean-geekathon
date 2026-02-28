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

    # WeatherAPI.com condition codes for snow, ice, sleet, freezing conditions
    # Full set: patchy snow, light snow, moderate snow, heavy snow, ice pellets,
    # blizzard, freezing rain, freezing drizzle, sleet, blowing snow
    _SNOW_ICE_CODES = {
        1063, 1066, 1069, 1072,                              # patchy rain/snow/sleet/freezing
        1114, 1117,                                            # blowing snow, blizzard
        1147,                                                  # freezing fog
        1150, 1153, 1168, 1171,                               # drizzle, freezing drizzle
        1198, 1201,                                            # light/heavy freezing rain
        1204, 1207,                                            # light/heavy sleet
        1210, 1213, 1216, 1219, 1222, 1225,                   # snow (light→heavy)
        1237,                                                  # ice pellets
        1249, 1252,                                            # light/moderate sleet showers
        1255, 1258,                                            # light/moderate snow showers
        1261, 1264,                                            # light/moderate ice pellet showers
        1279, 1282,                                            # snow/ice with thunder
    }
    is_snow_ice = code in _SNOW_ICE_CODES

    # Fog codes — not snow/ice but hazardous for transport
    _FOG_CODES = {1030, 1135, 1147}
    is_fog = code in _FOG_CODES

    score = 0.0
    reasons: list[str] = []
    if wind_kph > 50 or gust_kph > 70:
        score += 45
        reasons.append(f"High wind ({wind_kph:.0f} km/h, gusts {gust_kph:.0f}): truck speed reductions and possible route closures")
    elif wind_kph > 30 or gust_kph > 50:
        score += 25
        reasons.append(f"Moderate wind ({wind_kph:.0f} km/h) may slow road freight")
    if precip_mm > 10:
        score += 30
        reasons.append(f"Heavy precipitation ({precip_mm:.1f} mm): road delays and visibility issues")
    elif precip_mm > 2:
        score += 15
        reasons.append(f"Precipitation ({precip_mm:.1f} mm) may cause minor delays")
    if vis_km < 1:
        score += 35
        reasons.append(f"Very low visibility ({vis_km:.1f} km): unsafe for road transport")
    elif vis_km < 5:
        score += 20
        reasons.append(f"Reduced visibility ({vis_km:.1f} km) may slow logistics")
    if is_snow_ice:
        score += 40
        reasons.append("Snow/ice conditions: significant transport disruption risk")
    if is_fog and not is_snow_ice:
        score += 25
        reasons.append("Fog: reduced visibility hazard for all transport modes")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons)
        if reasons
        else "No significant transport risk from current weather."
    )
    mitigation = None
    if level == RiskLevel.CRITICAL:
        mitigation = (
            "Halt non-essential dispatches. Confirm road/port closures with local authorities. "
            "Pre-position inventory at distribution centers. Activate alternate route plans."
        )
    elif level == RiskLevel.HIGH:
        mitigation = (
            "Delay non-urgent shipments. Verify road and port accessibility before dispatch. "
            "Consider alternate transport modes or routes."
        )
    elif level == RiskLevel.MODERATE:
        mitigation = "Monitor conditions closely. Allow buffer time for transit delays."
    return RiskFactor(
        factor="transportation",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind {wind_kph:.0f} km/h (gusts {gust_kph:.0f}), precip {precip_mm:.1f} mm, visibility {vis_km:.1f} km.",
        mitigation=mitigation,
    )


def _power_outage_risk(current: dict[str, Any]) -> RiskFactor:
    wind_kph = float(current.get("wind_kph") or 0)
    gust_kph = float(current.get("gust_kph") or wind_kph)
    precip_mm = float(current.get("precip_mm") or 0)
    condition = current.get("condition") or {}
    code = int(condition.get("code", 1000))
    # Thunderstorm codes: thunder, patchy rain/snow/ice with thunder
    _STORM_CODES = {1087, 1273, 1276, 1279, 1282}
    is_storm = code in _STORM_CODES or 2000 <= code <= 2300
    # Blizzard and heavy snow also threaten power lines
    _HEAVY_WINTER_CODES = {1117, 1219, 1222, 1225, 1258}
    is_heavy_winter = code in _HEAVY_WINTER_CODES

    score = 0.0
    reasons: list[str] = []
    if is_storm:
        score += 50
        reasons.append("Thunderstorms increase power outage and equipment damage risk")
    if is_heavy_winter:
        score += 35
        reasons.append("Heavy snow/blizzard: risk of power line damage and outages")
    if gust_kph > 60:
        score += 35
        reasons.append(f"Strong gusts ({gust_kph:.0f} km/h) can cause line damage and outages")
    elif wind_kph > 40:
        score += 20
        reasons.append(f"High wind ({wind_kph:.0f} km/h) may affect power infrastructure")
    if precip_mm > 15:
        score += 15
        reasons.append(f"Heavy rain ({precip_mm:.1f} mm) can cause local flooding and substation issues")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons) if reasons else "Low power outage risk from current weather."
    )
    mitigation = None
    if level == RiskLevel.CRITICAL:
        mitigation = (
            "Activate backup generators. Prioritize critical production loads. "
            "Coordinate with local utility for outage alerts and restoration ETAs."
        )
    elif level == RiskLevel.HIGH:
        mitigation = (
            "Test backup power systems. Prioritize critical loads. "
            "Subscribe to utility outage notifications."
        )
    elif level == RiskLevel.MODERATE:
        mitigation = "Verify backup power readiness. Monitor storm tracking forecasts."
    return RiskFactor(
        factor="power_outage",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind gusts {gust_kph:.0f} km/h, precip {precip_mm:.1f} mm, storm-related codes considered.",
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
    if level == RiskLevel.CRITICAL:
        mitigation = (
            "Implement heat/cold emergency protocols. Halt outdoor operations. "
            "Adjust shift schedules. Ensure HVAC at maximum capacity and PPE compliance."
        )
    elif level == RiskLevel.HIGH:
        mitigation = (
            "Adjust shift times to avoid peak temperature hours. "
            "Ensure adequate HVAC, hydration stations, and PPE."
        )
    elif level == RiskLevel.MODERATE:
        mitigation = "Monitor worker heat/cold stress. Ensure break schedules are adhered to."
    return RiskFactor(
        factor="production",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Temp {temp_c:.1f}°C (feels like {feelslike_c:.1f}°C), humidity {humidity}%, UV index {uv_val}.",
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
    # Severe conditions that cause port/route closures: heavy rain, freezing rain,
    # sleet, snow, blizzard, ice pellets, thunderstorms with precipitation
    _SEVERE_CLOSURE_CODES = {
        1117,                                # blizzard
        1195, 1198, 1201,                    # heavy rain, light/heavy freezing rain
        1204, 1207,                          # light/heavy sleet
        1219, 1222, 1225,                    # moderate/heavy/blizzard snow
        1237, 1264,                          # ice pellets
        1273, 1276, 1279, 1282,              # thunderstorm variants
    }
    if code in _SEVERE_CLOSURE_CODES:
        score += 40
        reasons.append("Severe weather conditions: high port/route closure probability")

    score = _clamp_score(score)
    level = _level_from_score(score)
    summary = (
        "; ".join(reasons) if reasons else "No significant port or route closure risk."
    )
    mitigation = None
    if level == RiskLevel.CRITICAL:
        mitigation = (
            "Expect port/airport closures. Activate contingency routing. "
            "Plan for 3-5 day backlog. Pre-notify customers of potential delays."
        )
    elif level == RiskLevel.HIGH:
        mitigation = (
            "Check port and airport advisories before dispatch. "
            "Prepare alternative routing or transport modes. Allow 1-3 day buffer."
        )
    elif level == RiskLevel.MODERATE:
        mitigation = "Monitor port/airport status. Build extra transit time into schedules."
    return RiskFactor(
        factor="port_and_route",
        level=level,
        score=round(score, 1),
        summary=summary,
        details=f"Wind {wind_kph:.0f} km/h (gusts {gust_kph:.0f}), precip {precip_mm:.1f} mm, visibility {vis_km:.1f} km.",
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
