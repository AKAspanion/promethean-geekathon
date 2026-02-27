import random
from app.data.base import BaseDataSource, DataSourceResult


class MarketDataSource(BaseDataSource):
    def get_type(self) -> str:
        return "market"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        commodities = (params or {}).get("commodities") or [
            "steel",
            "copper",
            "oil",
            "grain",
            "semiconductors",
        ]
        results = []
        for commodity in commodities:
            price_change = (random.random() - 0.5) * 20
            results.append(
                self._create_result(
                    {
                        "commodity": commodity,
                        "currentPrice": random.randint(100, 1100),
                        "priceChange": price_change,
                        "priceChangePercent": price_change,
                        "trend": "up"
                        if price_change > 0
                        else "down"
                        if price_change < 0
                        else "stable",
                        "volatility": random.random() * 30,
                        "volume": random.randint(0, 1000000),
                        "marketSentiment": random.choice(
                            ["bullish", "bearish", "neutral"]
                        ),
                        "supplyLevel": random.choice(["low", "normal", "high"]),
                        "demandLevel": random.choice(["low", "normal", "high"]),
                    }
                )
            )
        return results
