import asyncio
import logging
from app.data.base import BaseDataSource, DataSourceResult
from app.services.external_api_cache import cached_get
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Geopolitical keywords tuned for supply chain risk types
_DEFAULT_KEYWORDS = [
    "supply chain disruption",
    "trade sanctions",
    "port strike",
    "factory shutdown",
    "natural disaster manufacturing",
]


class GDELTDataSource(BaseDataSource):
    """
    Fetches geopolitical event news from the GDELT Doc 2.0 API.
    No API key required — fully free.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)

    def get_type(self) -> str:
        return "gdelt"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        keywords = (params or {}).get("keywords") or _DEFAULT_KEYWORDS
        results: list[DataSourceResult] = []

        try:
            async with httpx.AsyncClient() as client:

                async def _fetch_keyword(keyword: str) -> list[dict]:
                    try:
                        r = await cached_get(
                            client,
                            BASE_URL,
                            params={
                                "query": keyword,
                                "mode": "artlist",
                                "maxrecords": 10,
                                "timespan": "3days",
                                "format": "json",
                            },
                            timeout=15.0,
                            service="gdelt",
                        )
                        if r.status_code != 200:
                            logger.warning(
                                "GDELT returned %d for keyword %r",
                                r.status_code,
                                keyword,
                            )
                            return []
                        return r.json().get("articles") or []
                    except Exception as exc:
                        logger.warning("GDELT keyword %r error: %s", keyword, exc)
                        return []

                # Fetch all keywords concurrently (cap at 5 to respect GDELT rate limits)
                all_articles = await asyncio.gather(
                    *[_fetch_keyword(kw) for kw in keywords[:5]]
                )
                for articles in all_articles:
                    for article in articles:
                        title = (article.get("title") or "").strip()
                        if not title:
                            continue
                        results.append(
                            self._create_result(
                                {
                                    "title": title,
                                    "description": None,
                                    "url": article.get("url"),
                                    "source": article.get("domain"),
                                    "publishedAt": article.get("seendate"),
                                    "author": None,
                                    "content": None,
                                },
                                metadata={
                                    "sourcecountry": article.get("sourcecountry"),
                                    "language": article.get("language"),
                                    "source_provider": "gdelt",
                                },
                            )
                        )
        except Exception as e:
            logger.exception("Error fetching GDELT news: %s", e)

        logger.info("GDELT: fetched %d articles", len(results))
        return results
