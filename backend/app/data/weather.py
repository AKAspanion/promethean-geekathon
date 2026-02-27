import logging
from app.data.base import BaseDataSource, DataSourceResult
from app.services.external_api_cache import cached_get
from app.config import settings
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.openweathermap.org/data/2.5"


class WeatherDataSource(BaseDataSource):
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._api_key = (config or {}).get("apiKey") or settings.weather_api_key or ""
        if not self._api_key:
            self._api_key = ""
            logger.warning(
                "Weather API key not configured. "
                "Set WEATHER_API_KEY in .env. Using mock data."
            )

    def get_type(self) -> str:
        return "weather"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    def _mock_result(self, city: str) -> DataSourceResult:
        import random

        return self._create_result(
            {
                "city": city,
                "country": "US",
                "temperature": random.randint(10, 40),
                "condition": random.choice(["Clear", "Clouds", "Rain", "Storm"]),
                "description": "Mock weather data",
                "humidity": random.randint(0, 100),
                "windSpeed": random.random() * 20,
                "visibility": 10000,
                "coordinates": {
                    "lat": random.random() * 180 - 90,
                    "lon": random.random() * 360 - 180,
                },
            }
        )

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        cities = (params or {}).get("cities") or [
            "New York",
            "London",
            "Tokyo",
            "Mumbai",
            "Shanghai",
        ]
        results = []
        async with httpx.AsyncClient() as client:
            for city in cities:
                try:
                    if self._api_key:
                        r = await cached_get(
                            client,
                            f"{BASE_URL}/weather",
                            params={
                                "q": city,
                                "appid": self._api_key,
                                "units": "metric",
                            },
                            timeout=10.0,
                            service="weather",
                        )
                        if r.status_code == 200:
                            w = r.json()
                            results.append(
                                self._create_result(
                                    {
                                        "city": w.get("name", city),
                                        "country": w.get("sys", {}).get("country", ""),
                                        "temperature": w.get("main", {}).get("temp"),
                                        "condition": (w.get("weather") or [{}])[0].get(
                                            "main", ""
                                        ),
                                        "description": (w.get("weather") or [{}])[
                                            0
                                        ].get("description", ""),
                                        "humidity": w.get("main", {}).get("humidity"),
                                        "windSpeed": (w.get("wind") or {}).get(
                                            "speed", 0
                                        ),
                                        "visibility": w.get("visibility"),
                                        "coordinates": {
                                            "lat": w.get("coord", {}).get("lat"),
                                            "lon": w.get("coord", {}).get("lon"),
                                        },
                                    }
                                )
                            )
                        else:
                            results.append(self._mock_result(city))
                    else:
                        results.append(self._mock_result(city))
                except Exception as e:
                    logger.exception(
                        "Error fetching weather for %s: %s",
                        city,
                        e,
                    )
                    results.append(self._mock_result(city))
        return results
