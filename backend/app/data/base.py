from abc import ABC, abstractmethod
from datetime import datetime


class DataSourceResult:
    def __init__(self, source_type: str, data: dict, metadata: dict | None = None):
        self.source_type = source_type
        self.timestamp = datetime.utcnow()
        self.data = data
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "sourceType": self.source_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata,
        }


class BaseDataSource(ABC):
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._initialized = False

    async def initialize(self, config: dict | None = None) -> None:
        if config:
            self.config = config
        await self._on_initialize()
        self._initialized = True

    @abstractmethod
    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        pass

    @abstractmethod
    def get_type(self) -> str:
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        pass

    @abstractmethod
    async def _on_initialize(self) -> None:
        pass

    def _create_result(
        self, data: dict, metadata: dict | None = None
    ) -> DataSourceResult:
        return DataSourceResult(self.get_type(), data, metadata)
