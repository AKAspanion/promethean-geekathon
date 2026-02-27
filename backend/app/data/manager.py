import logging
from typing import Any

from app.data.weather import WeatherDataSource
from app.data.news import NewsDataSource
from app.data.traffic import TrafficDataSource
from app.data.market import MarketDataSource
from app.data.shipping import ShippingRoutesDataSource

logger = logging.getLogger(__name__)


class DataSourceManager:
    def __init__(self):
        self._sources: dict[str, Any] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        weather = WeatherDataSource()
        await weather.initialize({})
        self._sources[weather.get_type()] = weather
        news = NewsDataSource()
        await news.initialize({})
        self._sources[news.get_type()] = news
        traffic = TrafficDataSource()
        await traffic.initialize({})
        self._sources[traffic.get_type()] = traffic
        market = MarketDataSource()
        await market.initialize({})
        self._sources[market.get_type()] = market
        shipping = ShippingRoutesDataSource()
        await shipping.initialize({})
        self._sources[shipping.get_type()] = shipping
        self._initialized = True

    def get_source(self, type_name: str):
        return self._sources.get(type_name)

    async def fetch_by_types(
        self, types: list[str], params: dict | None = None
    ) -> dict[str, list[dict]]:
        await self.initialize()
        logger.info("fetchDataSourcesByTypes started: %s", ", ".join(types))
        results: dict[str, list[dict]] = {}
        for type_name in types:
            source = self._sources.get(type_name)
            if not source:
                logger.warning('Data source "%s": not registered', type_name)
                results[type_name] = []
                continue
            try:
                if await source.is_available():
                    data = await source.fetch_data(params)
                    # Normalize to list of dicts (like Nest: sourceType, timestamp, data)
                    results[type_name] = [r.to_dict() for r in data]
                    logger.info(
                        'Data source "%s": fetched %d items', type_name, len(data)
                    )
                else:
                    results[type_name] = []
            except Exception:
                logger.exception('Data source "%s": fetch failed', type_name)
                results[type_name] = []
        return results


_data_source_manager: DataSourceManager | None = None


def get_data_source_manager() -> DataSourceManager:
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager
