"""NewsAPI data source for the News Agent.

Request budget: at most 3 HTTP calls per fetch_data invocation.

  Request 1 — /top-headlines  (conflict + supply-chain breaking terms, OR-combined)
  Request 2 — /top-headlines  (entity-specific terms: supplier name, OEM, region conflict)
  Request 3 — /everything     (entity-specific + commodity, date-filtered for recency)

Using NewsAPI's boolean OR syntax to pack many keywords into each query string
avoids the per-keyword fan-out that caused 429 rate-limit errors.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.data.base import BaseDataSource, DataSourceResult
from app.services.external_api_cache import cached_get

logger = logging.getLogger(__name__)
BASE_URL = "https://newsapi.org/v2"

# Restrict /everything queries to articles published within this many days
_LOOKBACK_DAYS = 3
# Concurrency cap — never fire more than this many simultaneous NewsAPI requests
_MAX_CONCURRENT = 3
# Articles per request
_PAGE_SIZE = 20

# Terms that indicate geopolitical/conflict content — prioritised in headlines query
_CONFLICT_PREFIXES = ("attack", "war", "conflict", "sanction", "military", "armed")

# Base supply-chain terms always included in the breaking-news headline query
_BASE_HEADLINE_TERMS = ["attack", "sanctions", "supply chain", "manufacturing disruption"]


def _build_or_query(terms: list[str], max_terms: int = 8) -> str:
    """Join terms into a NewsAPI boolean OR query string.

    Multi-word terms are wrapped in double quotes so NewsAPI treats them as
    exact phrases rather than independent tokens.
    """
    parts: list[str] = []
    for t in terms[:max_terms]:
        t = t.strip()
        if not t:
            continue
        parts.append(f'"{t}"' if " " in t else t)
    return " OR ".join(parts)


def _bucket_keywords(keywords: list[str]) -> tuple[list[str], list[str]]:
    """Split a flat keyword list into (conflict_terms, entity_terms).

    conflict_terms — war/conflict/sanction phrases → headline query
    entity_terms   — supplier/OEM names, commodities, region-specific conflict phrases
    """
    conflict: list[str] = []
    entity: list[str] = []
    generic = {"supply chain", "manufacturing", "logistics", "shipping", "supply chain war", "military attack"}
    for kw in keywords:
        kw_lower = kw.lower()
        if any(kw_lower.startswith(p) for p in _CONFLICT_PREFIXES):
            conflict.append(kw)
        elif kw not in generic:
            entity.append(kw)
    return conflict, entity


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
        keywords: list[str] = (params or {}).get("keywords") or [
            "supply chain",
            "manufacturing",
            "logistics",
            "shipping",
        ]

        if not self._api_key:
            return self._mock_results()

        from_date = (
            datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%d")

        conflict_terms, entity_terms = _bucket_keywords(keywords)

        # ── Build at most 3 consolidated queries ──────────────────────
        # Query 1: /top-headlines — conflict/war + base supply-chain terms (breaking news)
        q_conflict_headlines = _build_or_query(
            (_BASE_HEADLINE_TERMS + conflict_terms)[:8]
        )

        # Query 2: /top-headlines — entity-specific (supplier name, OEM, region war)
        q_entity_headlines = _build_or_query(entity_terms[:6]) if entity_terms else ""

        # Query 3: /everything (date-filtered) — entity + conflict for recent in-depth coverage
        q_entity_everything = _build_or_query(
            (entity_terms + conflict_terms)[:8]
        ) if (entity_terms or conflict_terms) else ""

        results: list[DataSourceResult] = []
        sem = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _headlines(q: str) -> list[dict]:
            if not q:
                return []
            async with sem:
                try:
                    async with httpx.AsyncClient() as client:
                        r = await cached_get(
                            client,
                            f"{BASE_URL}/top-headlines",
                            params={
                                "q": q,
                                "apiKey": self._api_key,
                                "pageSize": _PAGE_SIZE,
                                "language": "en",
                            },
                            timeout=12.0,
                            service="news_headlines",
                        )
                    if r.status_code == 200:
                        arts = r.json().get("articles") or []
                        logger.info(
                            "NewsAPI /top-headlines q=%r → %d articles", q[:60], len(arts)
                        )
                        return arts
                    logger.warning(
                        "NewsAPI /top-headlines → %d (q=%r)", r.status_code, q[:60]
                    )
                except Exception as exc:
                    logger.warning("NewsAPI /top-headlines error: %s", exc)
            return []

        async def _everything(q: str) -> list[dict]:
            if not q:
                return []
            async with sem:
                try:
                    async with httpx.AsyncClient() as client:
                        r = await cached_get(
                            client,
                            f"{BASE_URL}/everything",
                            params={
                                "q": q,
                                "apiKey": self._api_key,
                                "sortBy": "publishedAt",
                                "pageSize": _PAGE_SIZE,
                                "language": "en",
                                "from": from_date,
                            },
                            timeout=12.0,
                            service="news",
                        )
                    if r.status_code == 200:
                        arts = r.json().get("articles") or []
                        logger.info(
                            "NewsAPI /everything q=%r → %d articles", q[:60], len(arts)
                        )
                        return arts
                    logger.warning(
                        "NewsAPI /everything → %d (q=%r)", r.status_code, q[:60]
                    )
                except Exception as exc:
                    logger.warning("NewsAPI /everything error: %s", exc)
            return []

        try:
            batches = await asyncio.gather(
                _headlines(q_conflict_headlines),
                _headlines(q_entity_headlines),
                _everything(q_entity_everything),
            )
            for articles in batches:
                for article in articles:
                    results.append(
                        self._create_result(
                            {
                                "title": article.get("title"),
                                "description": article.get("description"),
                                "url": article.get("url"),
                                "source": (article.get("source") or {}).get("name"),
                                "publishedAt": article.get("publishedAt"),
                                "author": article.get("author"),
                                "content": article.get("content"),
                            }
                        )
                    )
            logger.info("NewsDataSource: %d raw articles from 3 requests", len(results))
        except Exception as exc:
            logger.exception("NewsDataSource fetch_data error: %s", exc)

        return results if results else self._mock_results()

    # ── Broad headline scan (no keyword filter) ─────────────────────────

    async def fetch_broad_headlines(
        self,
        categories: list[str] | None = None,
    ) -> list[DataSourceResult]:
        """Fetch top headlines by category WITHOUT keyword filtering.

        Returns raw headlines — the caller is responsible for semantic
        matching against the supplier keyword pool.  Two requests are made
        (business + general) to capture breaking events that keyword-based
        queries would miss (e.g. "Earthquake in Taiwan" when the keyword
        pool only contains "TSMC" or "semiconductors").
        """
        if not self._api_key:
            return []

        cats = categories or ["business", "general"]
        results: list[DataSourceResult] = []

        async with httpx.AsyncClient() as client:
            async def _fetch_cat(cat: str) -> list[dict]:
                try:
                    r = await cached_get(
                        client,
                        f"{BASE_URL}/top-headlines",
                        params={
                            "category": cat,
                            "apiKey": self._api_key,
                            "pageSize": 50,
                            "language": "en",
                        },
                        timeout=12.0,
                        service="news_broad_headlines",
                    )
                    if r.status_code == 200:
                        arts = r.json().get("articles") or []
                        logger.info(
                            "NewsAPI /top-headlines (broad, cat=%s) → %d articles",
                            cat, len(arts),
                        )
                        return arts
                    logger.warning(
                        "NewsAPI /top-headlines (broad, cat=%s) → %d",
                        cat, r.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "NewsAPI broad headlines (cat=%s) error: %s", cat, exc,
                    )
                return []

            batches = await asyncio.gather(*[_fetch_cat(c) for c in cats])
            for articles in batches:
                for article in articles:
                    results.append(
                        self._create_result(
                            {
                                "title": article.get("title"),
                                "description": article.get("description"),
                                "url": article.get("url"),
                                "source": (article.get("source") or {}).get("name"),
                                "publishedAt": article.get("publishedAt"),
                                "author": article.get("author"),
                                "content": article.get("content"),
                            }
                        )
                    )

        logger.info(
            "NewsDataSource broad headlines: %d articles from %d categories",
            len(results), len(cats),
        )
        return results

    # ── Fallback mock ──────────────────────────────────────────────────

    def _mock_results(self) -> list[DataSourceResult]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            self._create_result(
                {
                    "title": "Supply Chain Disruption in Southeast Asia",
                    "description": "Major shipping routes affected by weather conditions",
                    "source": "Supply Chain News",
                    "publishedAt": now,
                }
            ),
            self._create_result(
                {
                    "title": "Manufacturing Plant Closure Announced",
                    "description": "Factory shutdown due to supplier issues",
                    "source": "Manufacturing Today",
                    "publishedAt": now,
                }
            ),
        ]
