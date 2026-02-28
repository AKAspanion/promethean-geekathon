"""Trend Insights Agent — LangGraph implementation.

Graph topology
--------------
START
  ├─► build_queries ─► fetch_material  ─┐
  │                 ─► fetch_supplier  ─┼─► merge_trend ─► build_trend_items ─► trend_insight_llm ─► END
  │                 ─► fetch_global    ─┤
  └─► fetch_headlines ─────────────────┘

Keyword-based fetch nodes query NewsAPI (via TrendDataSource) for their scope.
The fetch_headlines node fetches broad /top-headlines (business + general)
and semantic-matches them against the supplier keyword pool (name, country,
region, commodities) to catch breaking events that keyword search misses.
The merge node deduplicates by normalised title.
The LLM node uses LangChain + ChatPromptTemplate to produce structured
TrendInsight dicts (scope / entity / risk_opportunity / severity / …).

Public entrypoint
-----------------
run_trend_agent_graph(suppliers, materials, oem_name) -> list[dict]
    Returns a list of insight dicts ready to be persisted as TrendInsight rows.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from app.data.news import NewsDataSource
from app.data.trends import TrendDataSource
from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State (reducer for trend_items: merge_trend receives 4 edges, so multiple updates possible)
# ---------------------------------------------------------------------------


def _trend_items_reducer(_current: list[dict], update: list[dict]) -> list[dict]:
    """Use the update (last write wins). Needed when merge_trend is invoked multiple times on fan-in."""
    return update


class TrendAgentState(TypedDict, total=False):
    # Inputs
    suppliers: list[dict]       # [{name, region, country, location, commodities}]
    materials: list[dict]       # [{material_name}]
    oem_name: str

    # Derived queries (built in the build_queries node)
    material_queries: list[str]
    supplier_queries: list[str]
    global_queries: list[str]

    # Raw fetch results per scope
    material_raw: list[dict]
    supplier_raw: list[dict]
    global_raw: list[dict]
    headlines_raw: list[dict]  # broad top-headlines filtered by supplier pool

    # Merged + deduplicated trend items (reducer: merge_trend can run multiple times when fan-in)
    trend_items: Annotated[list[dict], _trend_items_reducer]

    # Final structured insights
    insights: list[dict]


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def _build_material_queries(materials: list[dict]) -> list[str]:
    queries: list[str] = []
    for m in materials[:8]:
        name = (m.get("material_name") or "").strip()
        if name:
            queries.append(f"{name} supply chain price trends 2026")
            queries.append(f"{name} shortage disruption")
    return list(dict.fromkeys(queries))[:12]


def _build_supplier_queries(suppliers: list[dict]) -> list[str]:
    queries: list[str] = []
    for s in suppliers[:8]:
        name = (s.get("name") or "").strip()
        region = (s.get("region") or s.get("country") or "").strip()
        if name:
            queries.append(f"{name} supply chain disruption")
        if region:
            queries.append(f"{region} manufacturing logistics risk")
            queries.append(f"{region} war conflict sanctions")
    return list(dict.fromkeys(queries))[:16]


_DEFAULT_GLOBAL_QUERIES = [
    "global supply chain disruption 2026",
    "trade tariff geopolitical risk manufacturing",
    "shipping freight rates Red Sea 2026",
    "war armed conflict supply chain",
    "sanctions trade embargo 2026",
    "geopolitical tension manufacturing disruption",
]


# ---------------------------------------------------------------------------
# Parallel fetch nodes
# ---------------------------------------------------------------------------


async def _build_queries_node(state: TrendAgentState) -> TrendAgentState:
    """Derive search queries from supplier/material inputs."""
    mat_q = _build_material_queries(state.get("materials") or [])
    sup_q = _build_supplier_queries(state.get("suppliers") or [])
    logger.info(
        "build_queries: %d material, %d supplier, %d global queries",
        len(mat_q), len(sup_q), len(_DEFAULT_GLOBAL_QUERIES),
    )
    return {
        "material_queries": mat_q,
        "supplier_queries": sup_q,
        "global_queries": _DEFAULT_GLOBAL_QUERIES,
    }


async def _fetch_material_node(state: TrendAgentState) -> TrendAgentState:
    queries = state.get("material_queries") or []
    raw = await _fetch_scope(queries, "material")
    logger.info("fetch_material: %d items", len(raw))
    return {"material_raw": raw}


async def _fetch_supplier_node(state: TrendAgentState) -> TrendAgentState:
    queries = state.get("supplier_queries") or []
    raw = await _fetch_scope(queries, "supplier")
    logger.info("fetch_supplier: %d items", len(raw))
    return {"supplier_raw": raw}


async def _fetch_global_node(state: TrendAgentState) -> TrendAgentState:
    queries = state.get("global_queries") or _DEFAULT_GLOBAL_QUERIES
    raw = await _fetch_scope(queries, "global")
    logger.info("fetch_global: %d items", len(raw))
    return {"global_raw": raw}


async def _fetch_scope(queries: list[str], level: str) -> list[dict]:
    if not queries:
        return []
    try:
        source = TrendDataSource()
        await source.initialize({})
        results = await source.fetch_data(
            {f"{level}_queries": queries}
        )
        return [r.to_dict() if hasattr(r, "to_dict") else r for r in results]
    except Exception as exc:
        logger.exception("fetch_scope(%s) error: %s", level, exc)
        return []


# ---------------------------------------------------------------------------
# Broad headline scan — semantic match against supplier keyword pool
# ---------------------------------------------------------------------------

# Country-code aliases (shared with news agent, duplicated to avoid coupling)
_COUNTRY_ALIASES: dict[str, list[str]] = {
    "us": ["united states", "america", "usa"],
    "uk": ["united kingdom", "britain", "england"],
    "gb": ["united kingdom", "britain", "england"],
    "cn": ["china", "chinese", "beijing", "shanghai"],
    "tw": ["taiwan", "taiwanese", "taipei"],
    "jp": ["japan", "japanese", "tokyo"],
    "kr": ["south korea", "korean", "seoul"],
    "de": ["germany", "german", "berlin"],
    "in": ["india", "indian", "delhi", "mumbai"],
    "mx": ["mexico", "mexican"],
    "br": ["brazil", "brazilian"],
    "ru": ["russia", "russian", "moscow"],
    "ua": ["ukraine", "ukrainian", "kyiv"],
    "il": ["israel", "israeli"],
    "sa": ["saudi arabia", "saudi"],
    "ae": ["uae", "emirates", "dubai"],
    "sg": ["singapore"],
    "my": ["malaysia", "malaysian"],
    "th": ["thailand", "thai", "bangkok"],
    "vn": ["vietnam", "vietnamese"],
    "id": ["indonesia", "indonesian"],
    "ph": ["philippines", "filipino"],
    "tr": ["turkey", "turkish", "istanbul"],
    "eg": ["egypt", "egyptian", "cairo", "suez"],
    "cl": ["chile", "chilean"],
    "ir": ["iran", "iranian"],
    "iq": ["iraq", "iraqi"],
    "ye": ["yemen", "yemeni"],
    "mm": ["myanmar", "burmese"],
}


def _parse_commodities_str(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]


def _build_supplier_pool(suppliers: list[dict], materials: list[dict]) -> list[str]:
    """Build a flat keyword pool from ALL suppliers + materials for headline matching."""
    pool: set[str] = set()
    for s in suppliers:
        name = (s.get("name") or "").strip()
        if name and len(name) >= 3:
            pool.add(name.lower())
        for field in ("city", "country", "region", "location"):
            val = (s.get(field) or "").strip()
            if val and len(val) >= 3:
                pool.add(val.lower())
        code = (s.get("countryCode") or "").strip().lower()
        if code:
            for alias in _COUNTRY_ALIASES.get(code, []):
                pool.add(alias)
        for commodity in _parse_commodities_str(s.get("commodities")):
            if len(commodity) >= 3:
                pool.add(commodity.lower())
    for m in materials:
        name = (m.get("material_name") or "").strip()
        if name and len(name) >= 3:
            pool.add(name.lower())
    return list(pool)


def _headline_matches_pool(article: dict, keyword_pool: list[str]) -> bool:
    text = " ".join([
        article.get("title") or "",
        article.get("description") or article.get("summary") or "",
    ]).lower()
    if not text.strip():
        return False
    return any(kw in text for kw in keyword_pool)


async def _fetch_headlines_node(state: TrendAgentState) -> TrendAgentState:
    """Fetch broad top headlines and filter by semantic match against supplier/material pool.

    This catches breaking events (war, disasters, sanctions) that the
    keyword-based TrendDataSource queries would miss because they
    don't include the exact search phrase used by NewsAPI.
    """
    suppliers = state.get("suppliers") or []
    materials = state.get("materials") or []
    keyword_pool = _build_supplier_pool(suppliers, materials)
    if not keyword_pool:
        return {"headlines_raw": []}

    try:
        source = NewsDataSource()
        await source.initialize({})
        all_headlines = await source.fetch_broad_headlines()

        matched: list[dict] = []
        for result in all_headlines:
            raw = result.to_dict() if hasattr(result, "to_dict") else result
            if not isinstance(raw, dict):
                continue
            article = raw.get("data", raw) if isinstance(raw, dict) else raw
            if isinstance(article, dict) and _headline_matches_pool(article, keyword_pool):
                matched.append(raw)

        logger.info(
            "fetch_headlines (trend): %d scanned, %d matched supplier pool (%d keywords)",
            len(all_headlines), len(matched), len(keyword_pool),
        )
    except Exception as exc:
        logger.exception("fetch_headlines (trend) error: %s", exc)
        matched = []

    return {"headlines_raw": matched}


# ---------------------------------------------------------------------------
# Merge node — fan-in after parallel fetches
# ---------------------------------------------------------------------------


def _merge_trend_node(state: TrendAgentState) -> TrendAgentState:
    """Combine all fetch results and deduplicate by normalised title."""
    combined: list[dict] = []
    for key in ("material_raw", "supplier_raw", "global_raw", "headlines_raw"):
        combined.extend(state.get(key) or [])  # type: ignore[arg-type]

    seen: set[str] = set()
    unique: list[dict] = []
    for item in combined:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        title = (data.get("title") or "").strip().lower()
        if not title or title in seen:
            continue
        seen.add(title)
        unique.append(item)

    logger.info(
        "merge_trend: %d total → %d unique after dedup", len(combined), len(unique)
    )
    return {"trend_items": unique}


# ---------------------------------------------------------------------------
# Build items node — normalise raw dicts for the LLM prompt
# ---------------------------------------------------------------------------


def _build_trend_items_node(state: TrendAgentState) -> TrendAgentState:
    """Flatten DataSourceResult wrappers into plain article dicts."""
    normalised: list[dict] = []
    for item in state.get("trend_items") or []:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        normalised.append(
            {
                "title":        data.get("title") or "",
                "summary":      data.get("summary") or data.get("description") or "",
                "source":       data.get("source") or "Unknown",
                "published_at": data.get("published_at") or data.get("publishedAt") or "",
                "level":        data.get("level") or "global",
                "query":        data.get("query") or "",
                "url":          data.get("url"),
                "relevance_score": float(data.get("relevance_score") or 0.7),
            }
        )
    return {"trend_items": normalised}


# ---------------------------------------------------------------------------
# LLM node — LangChain prompt → structured insight list
# ---------------------------------------------------------------------------

_INSIGHT_PROMPT: ChatPromptTemplate | None = None


def _get_insight_prompt() -> ChatPromptTemplate:
    global _INSIGHT_PROMPT
    if _INSIGHT_PROMPT is None:
        _INSIGHT_PROMPT = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a Supply Chain Trend Intelligence Agent. "
                        "You receive a list of real-time and recent news/trend articles "
                        "(fetched from NewsAPI /everything, /top-headlines, and broad "
                        "headline scanning) plus the OEM's supplier and material context. "
                        "Your task is to generate structured trend insights "
                        "covering three scopes: material, supplier, and global.\n\n"
                        "RECENCY RULES:\n"
                        "- Each article includes a 'published_at' timestamp. Treat articles "
                        "published within the last 24 hours as breaking news — prioritise "
                        "them and assign higher confidence and severity where warranted.\n"
                        "- Articles from the last 3 days are recent; weight them more than "
                        "older background articles.\n"
                        "- Do NOT ignore a recent article simply because it is a single data "
                        "point — breaking events (e.g. war, factory shutdown, port closure) "
                        "can have immediate critical impact even without corroboration.\n\n"
                        "GEOGRAPHIC MAPPING RULES:\n"
                        "- The 'Suppliers context' section lists each supplier with their "
                        "name, country, region, and commodities. Cross-reference every "
                        "news article against these supplier locations.\n"
                        "- If an article mentions a country or region where a supplier "
                        "operates, create an insight with scope='supplier' and "
                        "entity_name set to that supplier's name.\n"
                        "- If an article discusses a commodity that a supplier provides, "
                        "it affects that supplier — even if the event is in a different "
                        "region (commodity supply chains are global).\n"
                        "- For events like war, natural disasters, sanctions, or port "
                        "closures: also consider indirect impact on trade routes and "
                        "neighbouring regions that connect to the supplier.\n"
                        "- Example: 'War in Ukraine' → check if any supplier is in "
                        "Ukraine, Russia, or neighbouring countries. If yes, create a "
                        "'critical' supplier insight. Also create a 'global' insight "
                        "for broader trade-route impact.\n\n"
                        "SEVERITY RULES FOR CONFLICT AND WAR:\n"
                        "- Active war or armed conflict in a supplier's region → severity "
                        "'critical', risk_opportunity 'risk'.\n"
                        "- Geopolitical tension, sanctions, or military exercises near key "
                        "trade routes or supplier regions → severity 'high'.\n\n"
                        "For EACH insight return:\n"
                        "  scope          — 'material' | 'supplier' | 'global'\n"
                        "  entity_name    — material name, supplier name, or 'Global'\n"
                        "  risk_opportunity — 'risk' | 'opportunity'\n"
                        "  title          — concise headline (max 15 words)\n"
                        "  description    — 2-4 sentences of context, citing the article date "
                        "if it is recent (e.g. 'As of Feb 28 2026, ...'). "
                        "Mention which supplier(s) are affected and why.\n"
                        "  predicted_impact — single plain string (e.g. '10% cost increase by Q3')\n"
                        "  time_horizon   — 'short-term' | 'medium-term' | 'long-term'\n"
                        "  severity       — 'low' | 'medium' | 'high' | 'critical'\n"
                        "  recommended_actions — array of 3-5 plain action strings\n"
                        "  source_articles — array of article title strings used as evidence\n"
                        "  confidence     — float 0-1 (higher when article is recent and from "
                        "a credible source)\n\n"
                        "Return ONLY valid JSON — an array of insight objects. "
                        "No markdown, no prose outside the JSON array."
                    ),
                ),
                (
                    "user",
                    (
                        "OEM: {oem_name}\n\n"
                        "=== Suppliers context (with locations and commodities) ===\n"
                        "{suppliers_json}\n\n"
                        "=== Materials context ===\n"
                        "{materials_json}\n\n"
                        "=== Trend articles (most recent first, max 40) ===\n"
                        "{trend_items_json}\n\n"
                        "Today's date: {today_date}\n\n"
                        "Generate 10-15 trend insights covering all three scopes "
                        "(material, supplier, global). For each supplier-scope insight, "
                        "set entity_name to the EXACT supplier name from the list above. "
                        "Prioritise the most recent and highest-impact events, especially "
                        "those that directly affect a supplier's country or commodity. "
                        "Return a JSON array."
                    ),
                ),
            ]
        )
    return _INSIGHT_PROMPT


async def _trend_insight_llm_node(state: TrendAgentState) -> TrendAgentState:
    items = state.get("trend_items") or []
    if not items:
        logger.warning("trend_insight_llm: no trend items — skipping LLM call")
        return {"insights": []}

    llm = get_chat_model()
    if not llm:
        logger.warning("trend_insight_llm: no LLM configured")
        return {"insights": []}

    prompt = _get_insight_prompt()
    chain = prompt | llm

    # Sort items by recency (most recent first) before passing to the LLM
    def _pub_sort_key(item: dict) -> str:
        return item.get("published_at") or item.get("publishedAt") or ""

    items_sorted = sorted(items, key=_pub_sort_key, reverse=True)
    today_date = datetime.now(timezone.utc).strftime("%B %d %Y")

    try:
        msg = await chain.ainvoke(
            {
                "oem_name":         state.get("oem_name") or "Unknown OEM",
                "suppliers_json":   json.dumps(state.get("suppliers") or [], indent=2),
                "materials_json":   json.dumps(state.get("materials") or [], indent=2),
                "trend_items_json": json.dumps(items_sorted[:40], indent=2),
                "today_date":       today_date,
            }
        )

        raw_text: str = (
            msg.content
            if isinstance(msg.content, str)
            else "".join(
                str(b.get("text") if isinstance(b, dict) else b)
                for b in msg.content
            )
        )

        parsed = _extract_json(raw_text)
        if isinstance(parsed, dict):
            # LLM may return {"insights": [...]} instead of bare array
            parsed = parsed.get("insights") or []
        if not isinstance(parsed, list):
            logger.warning("trend_insight_llm: unexpected parse result type %s", type(parsed))
            return {"insights": []}

        valid: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if not (item.get("title") or "").strip():
                continue
            valid.append(item)

        logger.info("trend_insight_llm: %d insights generated", len(valid))
        return {"insights": valid}

    except Exception as exc:
        logger.exception("trend_insight_llm LLM error: %s", exc)
        return {"insights": []}


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(TrendAgentState)

_builder.add_node("build_queries",      _build_queries_node)
_builder.add_node("fetch_material",     _fetch_material_node)
_builder.add_node("fetch_supplier",     _fetch_supplier_node)
_builder.add_node("fetch_global",       _fetch_global_node)
_builder.add_node("fetch_headlines",    _fetch_headlines_node)
_builder.add_node("merge_trend",        _merge_trend_node)
_builder.add_node("build_trend_items",  _build_trend_items_node)
_builder.add_node("trend_insight_llm",  _trend_insight_llm_node)

# START → build queries → parallel fetch fan-out (keyword-based)
# START → fetch_headlines (broad scan, no query dependencies)
_builder.add_edge(START,            "build_queries")
_builder.add_edge(START,            "fetch_headlines")
_builder.add_edge("build_queries",  "fetch_material")
_builder.add_edge("build_queries",  "fetch_supplier")
_builder.add_edge("build_queries",  "fetch_global")

# Parallel fetch fan-in → merge (all four sources)
_builder.add_edge("fetch_material",  "merge_trend")
_builder.add_edge("fetch_supplier",  "merge_trend")
_builder.add_edge("fetch_global",    "merge_trend")
_builder.add_edge("fetch_headlines", "merge_trend")

# Linear pipeline after merge
_builder.add_edge("merge_trend",       "build_trend_items")
_builder.add_edge("build_trend_items", "trend_insight_llm")
_builder.add_edge("trend_insight_llm", END)

TREND_GRAPH = _builder.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def run_trend_agent_graph(
    suppliers: list[dict],
    materials: list[dict],
    oem_name: str = "",
) -> list[dict]:
    """Run the Trend Insights LangGraph for a given supplier/material context.

    Returns a list of insight dicts with the same keys as the TrendInsight model:
    scope, entity_name, risk_opportunity, title, description, predicted_impact,
    time_horizon, severity, recommended_actions, source_articles, confidence.
    """
    initial_state: TrendAgentState = {
        "suppliers": suppliers,
        "materials": materials,
        "oem_name":  oem_name,
    }

    final_state = await TREND_GRAPH.ainvoke(initial_state)
    return final_state.get("insights") or []
