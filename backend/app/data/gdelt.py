import asyncio
import logging
from app.data.base import BaseDataSource, DataSourceResult
from app.services.external_api_cache import cached_get
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Set to False to disable GDELT fetching (e.g. during rate-limit issues)
GDELT_ENABLED = False

# Geopolitical keywords tuned for supply chain risk types — conflict/war first
_DEFAULT_KEYWORDS = [
    "attack",
    "armed conflict",
    "military conflict",
    "supply chain disruption",
    "trade sanctions",
    "port strike",
    "factory shutdown",
    "natural disaster manufacturing",
    "earthquake flood tsunami",
    "embargo tariff trade attack",
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
        if not GDELT_ENABLED:
            logger.info("GDELT: disabled via GDELT_ENABLED flag")
            return []

        keywords = (params or {}).get("keywords") or _DEFAULT_KEYWORDS
        results: list[DataSourceResult] = []

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                headers={"User-Agent": "SupplyChainMonitor/1.0"},
            ) as client:

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
                        data = r.json()
                        if not isinstance(data, dict):
                            logger.warning(
                                "GDELT unexpected response type %s for %r",
                                type(data).__name__,
                                keyword,
                            )
                            return []
                        return data.get("articles") or []
                    except Exception as exc:
                        logger.warning(
                            "GDELT keyword %r error [%s]: %r",
                            keyword,
                            type(exc).__name__,
                            exc,
                        )
                        return []

                # Fetch keywords sequentially with delay to avoid GDELT 429 rate limits
                keyword_articles: list[tuple[str, list[dict]]] = []
                for i, kw in enumerate(keywords[:5]):
                    if i > 0:
                        await asyncio.sleep(2.0)
                    articles = await _fetch_keyword(kw)
                    keyword_articles.append((kw, articles))

                for keyword, articles in keyword_articles:
                    for article in articles:
                        title = (article.get("title") or "").strip()
                        if not title:
                            continue
                        # Synthesize a description from metadata so downstream
                        # LLM agents have useful context even without article body
                        country = article.get("sourcecountry") or "Unknown region"
                        domain = article.get("domain") or "unknown source"
                        description = (
                            f"{title}. Reported by {domain} ({country}), "
                            f"matched on keyword \"{keyword}\"."
                        )
                        results.append(
                            self._create_result(
                                {
                                    "title": title,
                                    "description": description,
                                    "url": article.get("url"),
                                    "source": domain,
                                    "publishedAt": article.get("seendate"),
                                    "author": None,
                                    "content": None,
                                },
                                metadata={
                                    "sourcecountry": country,
                                    "language": article.get("language"),
                                    "source_provider": "gdelt",
                                    "matched_keyword": keyword,
                                },
                            )
                        )
        except Exception as e:
            logger.exception("Error fetching GDELT news: %s", e)

        logger.info("GDELT: fetched %d articles", len(results))
        return results
