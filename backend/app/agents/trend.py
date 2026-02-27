"""Trend Insights Agent — LangGraph implementation.

Graph topology
--------------
START
  ├─► fetch_material  ─┐
  ├─► fetch_supplier  ─┼─► merge_trend ─► build_trend_items ─► trend_insight_llm ─► END
  └─► fetch_global    ─┘

Each fetch node queries NewsAPI (via TrendDataSource) for its scope in parallel.
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
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from app.data.trends import TrendDataSource
from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


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

    # Merged + deduplicated trend items
    trend_items: list[dict]

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
    return list(dict.fromkeys(queries))[:12]


_DEFAULT_GLOBAL_QUERIES = [
    "global supply chain disruption 2026",
    "trade tariff geopolitical risk manufacturing",
    "shipping freight rates Red Sea 2026",
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
# Merge node — fan-in after parallel fetches
# ---------------------------------------------------------------------------


def _merge_trend_node(state: TrendAgentState) -> TrendAgentState:
    """Combine all three fetch results and deduplicate by normalised title."""
    combined: list[dict] = []
    for key in ("material_raw", "supplier_raw", "global_raw"):
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
                        "You receive a list of news/trend articles and the "
                        "OEM's supplier and material context. "
                        "Your task is to generate structured trend insights "
                        "covering three scopes: material, supplier, and global.\n\n"
                        "For EACH insight return:\n"
                        "  scope          — 'material' | 'supplier' | 'global'\n"
                        "  entity_name    — material name, supplier name, or 'Global'\n"
                        "  risk_opportunity — 'risk' | 'opportunity'\n"
                        "  title          — concise headline (max 15 words)\n"
                        "  description    — 2-4 sentences of context\n"
                        "  predicted_impact — single plain string (e.g. '10% cost increase by Q3')\n"
                        "  time_horizon   — 'short-term' | 'medium-term' | 'long-term'\n"
                        "  severity       — 'low' | 'medium' | 'high' | 'critical'\n"
                        "  recommended_actions — array of 3-5 plain action strings\n"
                        "  source_articles — array of article title strings used as evidence\n"
                        "  confidence     — float 0-1\n\n"
                        "Return ONLY valid JSON — an array of insight objects. "
                        "No markdown, no prose outside the JSON array."
                    ),
                ),
                (
                    "user",
                    (
                        "OEM: {oem_name}\n\n"
                        "Suppliers context:\n{suppliers_json}\n\n"
                        "Materials context:\n{materials_json}\n\n"
                        "Trend articles (max 30):\n{trend_items_json}\n\n"
                        "Generate 8-12 trend insights covering all three scopes "
                        "(material, supplier, global). Return a JSON array."
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

    try:
        msg = await chain.ainvoke(
            {
                "oem_name":         state.get("oem_name") or "Unknown OEM",
                "suppliers_json":   json.dumps(state.get("suppliers") or [], indent=2),
                "materials_json":   json.dumps(state.get("materials") or [], indent=2),
                "trend_items_json": json.dumps(items[:30], indent=2),
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
_builder.add_node("merge_trend",        _merge_trend_node)
_builder.add_node("build_trend_items",  _build_trend_items_node)
_builder.add_node("trend_insight_llm",  _trend_insight_llm_node)

# START → build queries → parallel fetch fan-out
_builder.add_edge(START,            "build_queries")
_builder.add_edge("build_queries",  "fetch_material")
_builder.add_edge("build_queries",  "fetch_supplier")
_builder.add_edge("build_queries",  "fetch_global")

# Parallel fetch fan-in → merge
_builder.add_edge("fetch_material", "merge_trend")
_builder.add_edge("fetch_supplier", "merge_trend")
_builder.add_edge("fetch_global",   "merge_trend")

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
