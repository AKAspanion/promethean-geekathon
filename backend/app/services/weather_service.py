"""WeatherAPI.com client for current, forecast, and historical weather (used by weather agent)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.weatherapi.com/v1"


def _location_query(city: str) -> str:
    return (city or "").strip() or ""


async def get_current_weather(city: str) -> dict[str, Any] | None:
    if not settings.weather_api_key:
        logger.warning("WEATHER_API_KEY not set")
        return None

    q = _location_query(city)
    if not q:
        return None
    params: dict[str, str | int] = {
        "key": settings.weather_api_key,
        "q": q,
        "aqi": "no",
    }
    url = f"{BASE_URL}/current.json"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                resolved = await _resolve_location(client, q)
                if resolved:
                    r2 = await client.get(
                        url,
                        params={
                            "key": settings.weather_api_key,
                            "q": resolved,
                            "aqi": "no",
                        },
                    )
                    r2.raise_for_status()
                    return r2.json()
            logger.error(
                "Weather API error: %s %s", e.response.status_code, e.response.text
            )
            return None
        except Exception as e:
            logger.exception("Weather API failed: %s", e)
            return None


async def _resolve_location(client: httpx.AsyncClient, q: str) -> str | None:
    try:
        r = await client.get(
            f"{BASE_URL}/search.json",
            params={"key": settings.weather_api_key, "q": q},
        )
        r.raise_for_status()
        data = r.json()
        if not data or not isinstance(data, list):
            return None
        first = data[0] if data else None
        if not first or not isinstance(first, dict):
            return None
        lat, lon = first.get("lat"), first.get("lon")
        if lat is not None and lon is not None:
            return f"{lat},{lon}"
        return first.get("name") or None
    except Exception as e:
        logger.debug("Search fallback failed for q=%s: %s", q, e)
        return None


async def get_historical_weather(city: str, date: str) -> dict[str, Any] | None:
    """Fetch historical weather for a city on a specific date (YYYY-MM-DD)."""
    if not settings.weather_api_key:
        return None
    q = _location_query(city)
    if not q:
        return None
    params: dict[str, str | int] = {
        "key": settings.weather_api_key,
        "q": q,
        "dt": date,
    }
    url = f"{BASE_URL}/history.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.exception("History API failed for %s on %s: %s", city, date, e)
            return None


async def get_forecast(city: str, days: int | None = None) -> dict[str, Any] | None:
    if not settings.weather_api_key:
        return None
    q = _location_query(city)
    if not q:
        return None
    weather_days = getattr(settings, "weather_days_forecast", 3)
    num_days = days or weather_days
    params: dict[str, str | int] = {
        "key": settings.weather_api_key,
        "q": q,
        "days": min(max(num_days, 1), 14),
        "aqi": "no",
        "alerts": "yes",
    }
    url = f"{BASE_URL}/forecast.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.exception("Forecast API failed: %s", e)
            return None
