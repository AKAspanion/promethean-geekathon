import asyncio
import logging
from app.data.base import BaseDataSource, DataSourceResult
from app.services.external_api_cache import cached_get
from app.config import settings
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://newsapi.org/v2"


class NewsDataSource(BaseDataSource):
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._api_key = (config or {}).get("apiKey") or settings.news_api_key or ""
        if not self._api_key:
            logger.warning("News API key not configured. Using mock data.")

    def get_type(self) -> str:
        return "news"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        keywords = (params or {}).get("keywords") or [
            "supply chain",
            "manufacturing",
            "logistics",
            "shipping",
        ]
        results = []
        if self._api_key:
            try:
                async with httpx.AsyncClient() as client:

                    async def _fetch_keyword(keyword: str):
                        try:
                            r = await cached_get(
                                client,
                                f"{BASE_URL}/everything",
                                params={
                                    "q": keyword,
                                    "apiKey": self._api_key,
                                    "sortBy": "publishedAt",
                                    "pageSize": 5,
                                },
                                timeout=10.0,
                                service="news",
                            )
                            if r.status_code == 200:
                                return r.json().get("articles") or []
                        except Exception as exc:
                            logger.warning("NewsAPI keyword %r error: %s", keyword, exc)
                        return []

                    # Fetch all keywords concurrently
                    all_articles = await asyncio.gather(
                        *[_fetch_keyword(kw) for kw in keywords]
                    )
                    for articles in all_articles:
                        for article in articles:
                            results.append(
                                self._create_result(
                                    {
                                        "title": article.get("title"),
                                        "description": article.get("description"),
                                        "url": article.get("url"),
                                        "source": (article.get("source") or {}).get(
                                            "name"
                                        ),
                                        "publishedAt": article.get("publishedAt"),
                                        "author": article.get("author"),
                                        "content": article.get("content"),
                                    }
                                )
                            )
            except Exception as e:
                logger.exception("Error fetching news: %s", e)
        if not results:
            for article in [
                {
                    "title": "Supply Chain Disruption in Southeast Asia",
                    "description": (
                        "Major shipping routes affected by weather conditions"
                    ),
                    "source": "Supply Chain News",
                    "publishedAt": __import__("datetime").datetime.utcnow().isoformat()
                    + "Z",
                },
                {
                    "title": "Manufacturing Plant Closure Announced",
                    "description": "Factory shutdown due to supplier issues",
                    "source": "Manufacturing Today",
                    "publishedAt": __import__("datetime").datetime.utcnow().isoformat()
                    + "Z",
                },
            ]:
                results.append(self._create_result(article))
        return results
