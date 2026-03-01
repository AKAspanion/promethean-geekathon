"""Unified trend/news data source.

Fetches news and trend signals relevant to:
  - A specific material (e.g. "copper price trends")
  - A specific supplier (e.g. "SteelCore Industries supply chain")
  - Global macro-level topics (e.g. "global trade disruption semiconductor")

Uses NewsAPI when a key is configured; falls back to rich mock data so the
demo works out-of-the-box without any external API key.

Request budget: at most 4 HTTP calls per fetch_data invocation.

  Request 1 — /top-headlines  (breaking global/conflict news, OR-combined query)
  Request 2 — /everything     (material queries OR-combined, date-filtered)
  Request 3 — /everything     (supplier queries OR-combined, date-filtered)
  Request 4 — /everything     (global macro queries OR-combined, date-filtered)

Using NewsAPI's boolean OR syntax to pack many individual search terms into
each query string avoids the per-term fan-out that caused 429 rate-limit errors.

Each result is normalised to:
  {
    "title":          str,
    "summary":        str,
    "source":         str,
    "published_at":   str (ISO-8601),
    "url":            str | None,
    "relevance_score": float (0-1),
    "level":          "material" | "supplier" | "global",
    "query":          str   (the search term used),
  }
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx

from app.config import settings
from app.data.base import BaseDataSource, DataSourceResult

logger = logging.getLogger(__name__)

TrendLevel = Literal["material", "supplier", "global"]

_NEWSAPI_BASE = "https://newsapi.org/v2"
_LOOKBACK_DAYS = 3
_PAGE_SIZE = 20
_MAX_CONCURRENT = 4

# Always included in the /top-headlines breaking-news query
_BREAKING_TERMS = [
    "attack", "armed conflict", "sanctions", "supply chain disruption",
    "trade tariff", "factory shutdown",
]


def _build_or_query(terms: list[str], max_terms: int = 8) -> str:
    """Join terms into a NewsAPI boolean OR query.

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


class TrendDataSource(BaseDataSource):
    """Fetches material/supplier/global news and trend items."""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._api_key: str = (config or {}).get("apiKey") or settings.news_api_key or ""
        if not self._api_key:
            logger.info("NEWS_API_KEY not set - TrendDataSource will use mock data.")

    def get_type(self) -> str:
        return "trends"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    # ── Main entry ────────────────────────────────────────────────────

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        """params keys (all optional):
        - material_queries: list[str]   material names or search phrases
        - supplier_queries: list[str]   supplier names or search phrases
        - global_queries:   list[str]   global macro topics
        """
        p = params or {}
        material_queries: list[str] = p.get("material_queries") or []
        supplier_queries: list[str] = p.get("supplier_queries") or []
        global_queries: list[str] = p.get("global_queries") or [
            "global supply chain risk",
            "trade disruption 2026",
            "manufacturing shortage",
        ]

        if not self._api_key:
            return self._mock_results(material_queries, supplier_queries, global_queries)

        from_date = (
            datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%d")

        sem = asyncio.Semaphore(_MAX_CONCURRENT)

        # Build one OR-combined query per scope bucket (max 8 terms each)
        q_material = _build_or_query(material_queries[:8])
        q_supplier = _build_or_query(supplier_queries[:8])
        q_global = _build_or_query(global_queries[:8])
        # Breaking-news headline query: fixed conflict terms + any global queries
        q_headlines = _build_or_query((_BREAKING_TERMS + global_queries)[:8])

        batches = await asyncio.gather(
            self._get_headlines(q_headlines, "global", sem),
            self._get_everything(q_material, "material", from_date, sem) if q_material else _empty(),
            self._get_everything(q_supplier, "supplier", from_date, sem) if q_supplier else _empty(),
            self._get_everything(q_global, "global", from_date, sem) if q_global else _empty(),
        )

        results: list[DataSourceResult] = []
        for batch in batches:
            results.extend(batch)

        if not results:
            results = self._mock_results(material_queries, supplier_queries, global_queries)

        logger.info(
            "TrendDataSource: %d results (4 requests: 1 headlines + 3 everything)",
            len(results),
        )
        return results

    # ── NewsAPI requests ──────────────────────────────────────────────

    async def _get_headlines(
        self, query: str, level: TrendLevel, sem: asyncio.Semaphore
    ) -> list[DataSourceResult]:
        """Fetch top-headlines — catches breaking events not yet indexed by /everything."""
        if not query:
            return []
        async with sem:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{_NEWSAPI_BASE}/top-headlines",
                        params={
                            "q": query,
                            "apiKey": self._api_key,
                            "pageSize": _PAGE_SIZE,
                            "language": "en",
                        },
                        timeout=12.0,
                    )
                if resp.status_code == 200:
                    articles = resp.json().get("articles") or []
                    logger.info(
                        "TrendDataSource /top-headlines q=%r → %d articles",
                        query[:60], len(articles),
                    )
                    return [
                        self._create_result(self._normalise_article(art, level, query))
                        for art in articles
                    ]
                logger.warning(
                    "TrendDataSource /top-headlines %d for q=%r: %s",
                    resp.status_code, query[:60], resp.text[:200],
                )
            except Exception as exc:
                logger.exception("TrendDataSource /top-headlines error: %s", exc)
        return []

    async def _get_everything(
        self,
        query: str,
        level: TrendLevel,
        from_date: str,
        sem: asyncio.Semaphore,
    ) -> list[DataSourceResult]:
        """Fetch recent articles via /everything with a date lower bound."""
        if not query:
            return []
        async with sem:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{_NEWSAPI_BASE}/everything",
                        params={
                            "q": query,
                            "apiKey": self._api_key,
                            "sortBy": "publishedAt",
                            "pageSize": _PAGE_SIZE,
                            "language": "en",
                            "from": from_date,
                        },
                        timeout=12.0,
                    )
                if resp.status_code == 200:
                    articles = resp.json().get("articles") or []
                    logger.info(
                        "TrendDataSource /everything q=%r → %d articles",
                        query[:60], len(articles),
                    )
                    return [
                        self._create_result(self._normalise_article(art, level, query))
                        for art in articles
                    ]
                logger.warning(
                    "TrendDataSource /everything %d for q=%r: %s",
                    resp.status_code, query[:60], resp.text[:200],
                )
            except Exception as exc:
                logger.exception("TrendDataSource /everything error: %s", exc)
        return self._mock_for_query(query, level)

    # ── Legacy compatibility shim ─────────────────────────────────────

    async def _fetch_for_query(
        self, query: str, level: TrendLevel
    ) -> list[DataSourceResult]:
        from_date = (
            datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%d")
        sem = asyncio.Semaphore(1)
        return await self._get_everything(query, level, from_date, sem)

    # ── Normalisers ───────────────────────────────────────────────────

    @staticmethod
    def _normalise_article(art: dict, level: TrendLevel, query: str) -> dict:
        return {
            "title": art.get("title") or "",
            "summary": art.get("description") or art.get("content") or "",
            "source": (art.get("source") or {}).get("name") or "Unknown",
            "published_at": art.get("publishedAt")
            or datetime.now(timezone.utc).isoformat(),
            "url": art.get("url"),
            "relevance_score": 0.8,
            "level": level,
            "query": query,
        }

    # ── Mock data ─────────────────────────────────────────────────────

    def _mock_for_query(self, query: str, level: TrendLevel) -> list[DataSourceResult]:
        now = datetime.now(timezone.utc)
        items = _MOCK_ARTICLES.get(level, [])
        q_lower = query.lower()
        matched = [
            a for a in items if any(w in a["title"].lower() for w in q_lower.split())
        ]
        if not matched:
            matched = items[:3]
        out = []
        for i, art in enumerate(matched[:3]):
            out.append(
                self._create_result(
                    {
                        **art,
                        "published_at": (now - timedelta(hours=i * 6)).isoformat() + "Z",
                        "relevance_score": 0.7 - i * 0.05,
                        "level": level,
                        "query": query,
                    }
                )
            )
        return out

    def _mock_results(
        self,
        material_queries: list[str],
        supplier_queries: list[str],
        global_queries: list[str],
    ) -> list[DataSourceResult]:
        results: list[DataSourceResult] = []
        for q in material_queries or ["steel price", "semiconductor supply"]:
            results.extend(self._mock_for_query(q, "material"))
        for q in supplier_queries or ["supplier disruption"]:
            results.extend(self._mock_for_query(q, "supplier"))
        for q in global_queries or ["global trade risk"]:
            results.extend(self._mock_for_query(q, "global"))
        return results


async def _empty() -> list:
    """No-op coroutine returning an empty list (used in place of skipped gather slots)."""
    return []


# ── Rich mock article library ─────────────────────────────────────────

_MOCK_ARTICLES: dict[str, list[dict]] = {
    "material": [
        {
            "title": "Steel Prices Surge Amid Chinese Export Restrictions",
            "summary": (
                "Chinese government announces new export quotas on steel and iron ore, "
                "pushing global hot-rolled coil prices up 12% in Q1. Automotive and "
                "construction sectors brace for margin pressure."
            ),
            "source": "Metal Bulletin",
            "url": None,
        },
        {
            "title": "Semiconductor Shortage to Persist Through 2025, Analysts Warn",
            "summary": (
                "Leading-edge chip capacity remains constrained as TSMC and Samsung "
                "capital investment cycles lag demand growth from AI and EV sectors. "
                "Automakers face extended allocation queues."
            ),
            "source": "IC Insights",
            "url": None,
        },
        {
            "title": "Copper Demand Outlook Upgraded on EV Battery Boom",
            "summary": (
                "BloombergNEF raises copper demand forecast by 8% citing faster-than-expected "
                "EV adoption in Europe and China. Chilean mining output constrained by drought "
                "and water-use regulations."
            ),
            "source": "Bloomberg NEF",
            "url": None,
        },
        {
            "title": "Lithium Carbonate Spot Price Hits 18-Month High",
            "summary": (
                "Spot lithium carbonate prices jumped 23% month-on-month as battery gigafactory "
                "ramp-ups in the US and EU accelerate procurement. Bolivian nationalisation "
                "policy clouds long-term supply."
            ),
            "source": "Benchmark Mineral Intelligence",
            "url": None,
        },
        {
            "title": "Natural Rubber Supply Tightens as La Niña Returns",
            "summary": (
                "Meteorologists confirm a La Niña pattern through H2, raising risks of heavy "
                "rainfall in Thailand and Malaysia. Tyre makers increasing safety stock "
                "buffers by 30 days."
            ),
            "source": "Rubber World",
            "url": None,
        },
        {
            "title": "Rare Earth Export Controls Tightened by China",
            "summary": (
                "Beijing restricts exports of dysprosium and terbium, critical for permanent "
                "magnets in EVs and wind turbines. Prices surge; Western buyers scramble to "
                "qualify alternative sources in Australia and Canada."
            ),
            "source": "Reuters Commodities",
            "url": None,
        },
        {
            "title": "Cobalt Prices Fall as DRC Production Recovers",
            "summary": (
                "Democratic Republic of Congo cobalt output rebounds after safety improvements, "
                "pushing cathode-grade prices down 15%. Battery makers reassessing hedging "
                "strategies amid volatile market."
            ),
            "source": "Mining Journal",
            "url": None,
        },
        {
            "title": "Graphite Anode Supply Chain Under Scrutiny",
            "summary": (
                "US Department of Energy flags synthetic graphite as critical mineral risk. "
                "China controls 80% of anode-grade graphite processing; alternative projects "
                "in Mozambique and Tanzania at early stage."
            ),
            "source": "S&P Global",
            "url": None,
        },
    ],
    "supplier": [
        {
            "title": "TSMC Warns of Force Majeure Risk if Taiwan Strait Tensions Escalate",
            "summary": (
                "TSMC annual report discloses geopolitical risk scenarios that could trigger "
                "force majeure clauses with major OEM customers. Apple, NVIDIA, and Qualcomm "
                "begin qualifying secondary foundry options."
            ),
            "source": "DigiTimes",
            "url": None,
        },
        {
            "title": "Chinese Steel Mills Cut Output Amid Energy Rationing",
            "summary": (
                "Power grid constraints in Hebei and Shandong provinces force rolling production "
                "cuts at major integrated mills. Overseas buyers facing 4-6 week delays on "
                "confirmed orders."
            ),
            "source": "World Steel Association",
            "url": None,
        },
        {
            "title": "Labour Strike at Chilean Copper Mine Enters Third Week",
            "summary": (
                "Workers at Escondida, the world's largest copper mine, continue industrial "
                "action over wage negotiations. Codelco estimates 40,000 tonnes of lost "
                "production; spot premiums widening."
            ),
            "source": "Mining.com",
            "url": None,
        },
        {
            "title": "Semiconductor Supplier Diversification: Samsung Expands Texas Fab",
            "summary": (
                "Samsung Electronics breaks ground on second advanced logic fab in Taylor, "
                "Texas under CHIPS Act incentives. Initial capacity targeted at 2nm process "
                "for automotive and AI applications by 2027."
            ),
            "source": "EE Times",
            "url": None,
        },
        {
            "title": "Malaysian Rubber Producers Request Emergency Government Support",
            "summary": (
                "Rising fertilizer and energy costs squeeze Malaysian smallholder rubber farmers. "
                "The Rubber Industry Smallholders Development Authority requests $120M subsidy "
                "package to maintain output levels."
            ),
            "source": "The Star Malaysia",
            "url": None,
        },
        {
            "title": "Battery Material Supplier BYD Secures New Lithium Mines in Bolivia",
            "summary": (
                "Chinese EV giant BYD signs 20-year offtake agreement with state-owned Yacimientos "
                "de Litio Bolivianos. Deal raises concerns among Western OEMs about Chinese vertical "
                "integration of battery supply."
            ),
            "source": "Financial Times",
            "url": None,
        },
    ],
    "global": [
        {
            "title": "Red Sea Crisis: Shipping Delays Now Averaging 18 Extra Days",
            "summary": (
                "Continued Houthi attacks force 90% of container vessels to reroute via Cape of "
                "Good Hope. Freight rates on Asia-Europe lanes up 340% year-on-year; insurers "
                "declare heightened war-risk zone surcharges."
            ),
            "source": "Lloyd's List",
            "url": None,
        },
        {
            "title": "G7 Agrees Critical Minerals Supply Chain Resilience Framework",
            "summary": (
                "G7 leaders endorse a joint critical minerals strategy targeting 50% reduction in "
                "dependency on single-source suppliers for lithium, cobalt, and rare earths by 2030. "
                "Investment guarantees of $30B announced."
            ),
            "source": "Reuters",
            "url": None,
        },
        {
            "title": "US Imposes 25% Tariff on Imported Electric Vehicle Components",
            "summary": (
                "The Biden-Trump continuity tariff package extends Section 301 duties to EV "
                "drivetrain components from China. Supply chain teams rushing to re-source "
                "motors, inverters, and battery packs outside China."
            ),
            "source": "Wall Street Journal",
            "url": None,
        },
        {
            "title": "Climate Extremes Threaten Southeast Asian Manufacturing Hubs",
            "summary": (
                "Record monsoon flooding in Vietnam and Thailand disrupts electronics and "
                "automotive parts manufacturing. Insurance losses estimated at $4.2B; business "
                "continuity plans being stress-tested by multinationals."
            ),
            "source": "Swiss Re Institute",
            "url": None,
        },
        {
            "title": "EU Corporate Sustainability Due Diligence Directive Enters Force",
            "summary": (
                "CSDDD requires large EU companies to map and audit their full supply chains for "
                "human rights and environmental risks. Non-compliance penalties up to 5% of "
                "global turnover; implementation deadline 2027."
            ),
            "source": "European Commission",
            "url": None,
        },
        {
            "title": "Global Container Shortage Re-emerges as Port Congestion Spreads",
            "summary": (
                "Port delays at Rotterdam, Los Angeles, and Singapore have backed up container "
                "availability. Average box dwell times up 35%; spot rates climbing after "
                "18-month normalisation."
            ),
            "source": "Drewry Supply Chain Advisors",
            "url": None,
        },
        {
            "title": "Taiwan Strait Military Exercises Elevate Insurance Premiums",
            "summary": (
                "PLA naval exercises near Taiwan cause marine insurers to issue special advisories. "
                "Semiconductor OEMs and EMS companies accelerating dual-source qualification "
                "programs as contingency measure."
            ),
            "source": "South China Morning Post",
            "url": None,
        },
    ],
}
