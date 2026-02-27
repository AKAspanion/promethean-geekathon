import random
from app.data.base import BaseDataSource, DataSourceResult


class TrafficDataSource(BaseDataSource):
    def get_type(self) -> str:
        return "traffic"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        routes = (params or {}).get("routes") or [
            {"origin": "New York", "destination": "Los Angeles"},
            {"origin": "London", "destination": "Paris"},
            {"origin": "Tokyo", "destination": "Osaka"},
        ]
        results = []
        for route in routes:
            delay = random.randint(0, 120)
            congestion = random.choice(["low", "medium", "high", "severe"])
            results.append(
                self._create_result(
                    {
                        "origin": route["origin"],
                        "destination": route["destination"],
                        "estimatedDelay": delay,
                        "congestionLevel": congestion,
                        "averageSpeed": random.randint(20, 80),
                        "incidents": random.randint(0, 3),
                        "routeStatus": "delayed" if delay > 60 else "normal",
                    }
                )
            )
        return results
