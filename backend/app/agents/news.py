import json
import logging
import time
import uuid as _uuid
from typing import TypedDict, Literal
from uuid import UUID

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START

from app.database import SessionLocal
from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model
from app.services.llm_client import _persist_llm_log
from app.services.agent_types import OemScope
from app.services.oems import get_oem_by_id
from app.services.suppliers import get_by_id as get_supplier_by_id
from app.services.websocket_manager import manager as ws_manager
from app.data.news import NewsDataSource
from app.data.gdelt import GDELTDataSource

logger = logging.getLogger(__name__)


async def _broadcast_progress(
    step: str,
    message: str,
    context: str | None = None,
    details: dict | None = None,
    oem_name: str | None = None,
    supplier_name: str | None = None,
) -> None:
    """Broadcast a news agent progress event over websocket."""
    payload: dict = {
        "type": "news_agent_progress",
        "step": step,
        "message": message,
    }
    if context:
        payload["context"] = context
    if oem_name:
        payload["oemName"] = oem_name
    if supplier_name:
        payload["supplierName"] = supplier_name
    if details:
        payload["details"] = details
    await ws_manager.broadcast(payload)


class NewsItem(TypedDict):
    title: str | None
    description: str | None
    url: str | None
    source: str | None
    publishedAt: str | None
    author: str | None
    content: str | None


class EntityData(TypedDict, total=False):
    """Flat dict holding key attributes of an OEM or Supplier."""
    id: str
    name: str
    location: str | None
    city: str | None
    country: str | None
    countryCode: str | None
    region: str | None
    commodities: str | None


class NewsAgentState(TypedDict, total=False):
    scope: OemScope
    context: Literal["supplier", "global"]
    # OEM and supplier details fetched from DB
    oem_data: EntityData
    supplier_data: EntityData | None
    # Pre-fetched data passed from outside (backward compat)
    news_data: dict[str, list[dict]]
    # Per-source raw fetch results (populated by parallel fetch nodes)
    newsapi_raw: list[dict]
    gdelt_raw: list[dict]
    # Merged + normalised
    news_items: list[NewsItem]
    news_risks: list[dict]
    news_opportunities: list[dict]


# ---------------------------------------------------------------------------
# Helper to extract EntityData from a DB model
# ---------------------------------------------------------------------------

def _entity_from_model(obj) -> EntityData:
    """Build an EntityData dict from a SQLAlchemy OEM or Supplier model."""
    return EntityData(
        id=str(obj.id),
        name=getattr(obj, "name", "") or "",
        location=getattr(obj, "location", None),
        city=getattr(obj, "city", None),
        country=getattr(obj, "country", None),
        countryCode=getattr(obj, "countryCode", None),
        region=getattr(obj, "region", None),
        commodities=getattr(obj, "commodities", None),
    )


# ---------------------------------------------------------------------------
# Parse commodities string into a list
# ---------------------------------------------------------------------------

def _parse_commodities(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]


# ---------------------------------------------------------------------------
# Keyword helpers — driven by oem_data and supplier_data, NOT scope
# ---------------------------------------------------------------------------

def _newsapi_keywords(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> list[str]:
    base = ["supply chain", "manufacturing", "logistics", "shipping"]
    if oem_data:
        oem_name = oem_data.get("name")
        if oem_name:
            base.append(oem_name)
        for commodity in _parse_commodities(oem_data.get("commodities"))[:3]:
            base.append(f"{commodity} supply chain")
        oem_city = oem_data.get("city")
        if oem_city:
            base.append(f"supply chain {oem_city}")
        oem_country = oem_data.get("countryCode") or oem_data.get("country")
        if oem_country:
            base.append(f"supply chain {oem_country}")
    if supplier_data:
        supplier_name = supplier_data.get("name")
        if supplier_name:
            base.append(supplier_name)
        for commodity in _parse_commodities(supplier_data.get("commodities"))[:3]:
            base.append(f"{commodity} supply chain")
        sup_city = supplier_data.get("city")
        if sup_city:
            base.append(f"supply chain {sup_city}")
        sup_country = supplier_data.get("countryCode") or supplier_data.get("country")
        if sup_country:
            base.append(f"supply chain {sup_country}")
    return base


def _gdelt_keywords(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> list[str]:
    base = [
        "supply chain disruption",
        "trade sanctions",
        "port strike",
        "factory shutdown",
        "natural disaster manufacturing",
    ]
    if oem_data:
        oem_name = oem_data.get("name")
        if oem_name:
            base.append(f"{oem_name} disruption")
        for commodity in _parse_commodities(oem_data.get("commodities"))[:2]:
            base.append(f"{commodity} shortage")
        oem_country = oem_data.get("countryCode") or oem_data.get("country")
        if oem_country:
            base.append(f"sanctions {oem_country}")
    if supplier_data:
        supplier_name = supplier_data.get("name")
        if supplier_name:
            base.append(f"{supplier_name} disruption")
        for commodity in _parse_commodities(supplier_data.get("commodities"))[:2]:
            base.append(f"{commodity} shortage")
        sup_country = supplier_data.get("countryCode") or supplier_data.get("country")
        if sup_country:
            base.append(f"sanctions {sup_country}")
    return base


def _entity_names(state: NewsAgentState) -> tuple[str | None, str | None]:
    """Return (oem_name, supplier_name) from state for broadcast payloads."""
    oem = state.get("oem_data")
    sup = state.get("supplier_data")
    return (
        oem.get("name") if oem else None,
        sup.get("name") if sup else None,
    )


# ---------------------------------------------------------------------------
# Parallel fetch nodes
# ---------------------------------------------------------------------------

async def _fetch_newsapi_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch articles from NewsAPI.org."""
    context = state.get("context", "supplier")
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)
    keywords = _newsapi_keywords(oem_data, supplier_data)
    logger.info("[NewsAgent:%s] Fetching from NewsAPI with %d keywords", context, len(keywords))
    await _broadcast_progress("fetch_newsapi", "Fetching articles from NewsAPI", context, oem_name=oem_name, supplier_name=supplier_name)
    try:
        source = NewsDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("[NewsAgent:%s] NewsAPI returned %d articles", context, len(raw))
        await _broadcast_progress(
            "fetch_newsapi_done", f"NewsAPI returned {len(raw)} articles",
            context, {"count": len(raw)}, oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[NewsAgent:%s] NewsAPI fetch error: %s", context, exc)
        await _broadcast_progress("fetch_newsapi_error", f"NewsAPI error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        raw = []
    return {"newsapi_raw": raw}


async def _fetch_gdelt_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch geopolitical event articles from GDELT (no API key required)."""
    context = state.get("context", "supplier")
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)
    keywords = _gdelt_keywords(oem_data, supplier_data)
    logger.info("[NewsAgent:%s] Fetching from GDELT with %d keywords", context, len(keywords))
    await _broadcast_progress("fetch_gdelt", "Fetching articles from GDELT", context, oem_name=oem_name, supplier_name=supplier_name)
    try:
        source = GDELTDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("[NewsAgent:%s] GDELT returned %d articles", context, len(raw))
        await _broadcast_progress(
            "fetch_gdelt_done", f"GDELT returned {len(raw)} articles",
            context, {"count": len(raw)}, oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[NewsAgent:%s] GDELT fetch error: %s", context, exc)
        await _broadcast_progress("fetch_gdelt_error", f"GDELT error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        raw = []
    return {"gdelt_raw": raw}


# ---------------------------------------------------------------------------
# Merge node — fan-in after parallel fetches
# ---------------------------------------------------------------------------

async def _merge_news_node(state: NewsAgentState) -> NewsAgentState:
    """
    Combine articles from all sources + any pre-fetched news_data.
    Deduplicates by normalised title to avoid redundant LLM tokens.
    """
    context = state.get("context", "supplier")
    oem_name, supplier_name = _entity_names(state)
    combined: list[dict] = []

    # Include legacy pre-fetched data passed from outside the graph
    external = state.get("news_data") or {}
    for item in external.get("news") or []:
        combined.append(item)

    for item in state.get("newsapi_raw") or []:
        combined.append(item)
    for item in state.get("gdelt_raw") or []:
        combined.append(item)

    # Deduplicate by normalised title
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for item in combined:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        title = (data.get("title") or "").strip().lower()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        unique.append(item)

    logger.info(
        "[NewsAgent:%s] Merged %d total -> %d unique articles after dedup",
        context, len(combined), len(unique),
    )
    await _broadcast_progress(
        "merge_done", f"Merged {len(unique)} unique articles (from {len(combined)} total)",
        context, {"total": len(combined), "unique": len(unique)},
        oem_name=oem_name, supplier_name=supplier_name,
    )
    # Store as a news_data dict so _build_news_items_node can consume it normally
    return {"news_data": {"news": unique}}


# ---------------------------------------------------------------------------
# Build news items node
# ---------------------------------------------------------------------------

async def _build_news_items_node(state: NewsAgentState) -> NewsAgentState:
    """Normalize raw news data into NewsItem structures."""
    context = state.get("context", "supplier")
    oem_name, supplier_name = _entity_names(state)
    raw = state.get("news_data") or {}
    items = raw.get("news") or []

    normalized: list[NewsItem] = []
    for item in items:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        normalized.append(
            {
                "title": data.get("title"),
                "description": data.get("description"),
                "url": data.get("url"),
                "source": data.get("source"),
                "publishedAt": data.get("publishedAt"),
                "author": data.get("author"),
                "content": data.get("content"),
            }
        )
    logger.info("[NewsAgent:%s] Normalized %d news items for LLM", context, len(normalized))
    await _broadcast_progress(
        "items_ready", f"Prepared {len(normalized)} articles for analysis",
        context, {"count": len(normalized)},
        oem_name=oem_name, supplier_name=supplier_name,
    )
    return {"news_items": normalized}


# ---------------------------------------------------------------------------
# Build OEM/supplier context string for LLM prompts
# ---------------------------------------------------------------------------

def _build_entity_context(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> str:
    """Build a human-readable context block describing the OEM and supplier."""
    parts: list[str] = []
    if oem_data:
        oem_name = oem_data.get("name") or "Unknown"
        oem_loc_parts = [
            p
            for p in [
                oem_data.get("city"),
                oem_data.get("country"),
                oem_data.get("region"),
            ]
            if p
        ]
        oem_loc = ", ".join(oem_loc_parts) if oem_loc_parts else "Unknown"
        oem_commodities = oem_data.get("commodities") or "N/A"
        parts.append(
            f"OEM: {oem_name}\n"
            f"  Location: {oem_loc}\n"
            f"  Commodities: {oem_commodities}"
        )
    if supplier_data:
        sup_name = supplier_data.get("name") or "Unknown"
        sup_loc_parts = [
            p
            for p in [
                supplier_data.get("city"),
                supplier_data.get("country"),
                supplier_data.get("region"),
            ]
            if p
        ]
        sup_loc = ", ".join(sup_loc_parts) if sup_loc_parts else "Unknown"
        sup_commodities = supplier_data.get("commodities") or "N/A"
        parts.append(
            f"Supplier: {sup_name}\n"
            f"  Location: {sup_loc}\n"
            f"  Commodities: {sup_commodities}"
        )
    return "\n".join(parts) if parts else "No entity context available."


def _get_llm():
    return get_chat_model()


def _build_supplier_prompt(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> ChatPromptTemplate:
    entity_context = _build_entity_context(oem_data, supplier_data)
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a News Agent for a manufacturing supply "
                    "chain. You receive news items about suppliers, "
                    "OEMs, and regions. Extract structured supply "
                    "chain risk signals using the following "
                    "risk types: factory_shutdown, labor_strike, "
                    "bankruptcy_risk, sanction_risk, "
                    "port_congestion, natural_disaster, "
                    "geopolitical_tension, regulatory_change, "
                    "infrastructure_failure, commodity_shortage, "
                    "cyber_incident.\n\n"
                    "Return ONLY valid JSON."
                ),
            ),
            (
                "user",
                (
                    "Analyze the following news items in the context "
                    "of this OEM and supplier.\n\n"
                    f"=== Entity Context ===\n{entity_context}\n\n"
                    "=== News Items ===\n{news_items_json}\n\n"
                    "Return JSON of shape:\n"
                    "{{\n"
                    '  "risks": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "severity": "low" | "medium" | '
                    '"high" | "critical",\n'
                    '      "affectedRegion": str | null,\n'
                    '      "affectedSupplier": str | null,\n'
                    '      "estimatedImpact": str | null,\n'
                    '      "estimatedCost": number | null,\n'
                    '      "risk_type": str,\n'
                    '      "source": str | null\n'
                    "    }}\n"
                    "  ],\n"
                    '  "opportunities": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "type": "cost_saving" | '
                    '"time_saving" | "quality_improvement" | '
                    '"market_expansion" | '
                    '"supplier_diversification",\n'
                    '      "affectedRegion": str | null,\n'
                    '      "potentialBenefit": str | null,\n'
                    '      "estimatedValue": number | null\n'
                    "    }}\n"
                    "  ]\n"
                    "}}\n"
                    "If none, use empty arrays."
                ),
            ),
        ]
    )


def _build_global_prompt(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> ChatPromptTemplate:
    entity_context = _build_entity_context(oem_data, supplier_data)
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a global supply chain News Agent. You "
                    "receive news about macro events (geopolitics, "
                    "trade, climate, logistics). Extract only "
                    "material global supply chain risks that could "
                    "affect the given OEM and supplier."
                ),
            ),
            (
                "user",
                (
                    "Analyze the following news items for global supply "
                    "chain risks relevant to this OEM and supplier.\n\n"
                    f"=== Entity Context ===\n{entity_context}\n\n"
                    "=== News Items ===\n{news_items_json}\n\n"
                    "Return JSON of shape:\n"
                    "{{\n"
                    '  "risks": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "severity": "low" | "medium" | '
                    '"high" | "critical",\n'
                    '      "affectedRegion": str | null,\n'
                    '      "affectedSupplier": null,\n'
                    '      "estimatedImpact": str | null,\n'
                    '      "estimatedCost": number | null,\n'
                    '      "risk_type": str,\n'
                    '      "source": str | null\n'
                    "    }}\n"
                    "  ],\n"
                    '  "opportunities": []\n'
                    "}}\n"
                    "If no material global risks, return "
                    '{{"risks": [], "opportunities": []}}.'
                ),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# LLM risk extraction node
# ---------------------------------------------------------------------------

async def _news_risk_llm_node(state: NewsAgentState) -> NewsAgentState:
    """
    Convert NewsItem list into risks and opportunities using LangChain.
    Builds prompts using oem_data and supplier_data from state.
    Returns empty lists when LLM is not configured.
    """
    items = state.get("news_items") or []
    if not items:
        return {"news_risks": [], "news_opportunities": []}

    llm = _get_llm()
    if not llm:
        return {"news_risks": [], "news_opportunities": []}

    context = state.get("context", "supplier") or "supplier"
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)

    if context == "supplier":
        prompt = _build_supplier_prompt(oem_data, supplier_data)
    else:
        prompt = _build_global_prompt(oem_data, supplier_data)

    chain = prompt | llm

    # Derive provider/model for logging
    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]

    items_json = json.dumps(items, indent=2)
    prompt_text = prompt.format(news_items_json=items_json)
    start = time.perf_counter()

    try:
        logger.info(
            "[NewsAgent:%s] LLM request id=%s provider=%s model=%s prompt_len=%d",
            context, call_id, provider, model_name, len(prompt_text),
        )
        await _broadcast_progress(
            "llm_start", f"Running {context} risk extraction",
            context, {"call_id": call_id, "provider": provider, "model": str(model_name)},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        msg = await chain.ainvoke({"news_items_json": items_json})
        elapsed = int((time.perf_counter() - start) * 1000)

        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block))
            raw_text = "".join(parts)

        logger.info(
            "[NewsAgent:%s] LLM response id=%s provider=%s elapsed_ms=%d response_len=%d",
            context, call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, raw_text, "success", elapsed, None,
        )

        parsed = _extract_json(raw_text) or {}
        raw_risks = parsed.get("risks") or []
        raw_opps = parsed.get("opportunities") or []

        risks: list[dict] = []
        opps: list[dict] = []

        for r in raw_risks:
            if not isinstance(r, dict):
                continue
            title = (str(r.get("title") or "")).strip()
            desc = (str(r.get("description") or "")).strip()
            if not title or not desc:
                continue
            risks.append(r)

        for o in raw_opps:
            if not isinstance(o, dict):
                continue
            title = (str(o.get("title") or "")).strip()
            desc = (str(o.get("description") or "")).strip()
            if not title or not desc:
                continue
            opps.append(o)

        logger.info(
            "[NewsAgent:%s] LLM extraction complete: risks=%d opportunities=%d elapsed_ms=%d",
            context, len(risks), len(opps), elapsed,
        )
        await _broadcast_progress(
            "llm_done", f"Extracted {len(risks)} risks and {len(opps)} opportunities",
            context, {"risks": len(risks), "opportunities": len(opps), "elapsed_ms": elapsed},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"news_risks": risks, "news_opportunities": opps}
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[NewsAgent:%s] LLM error: %s", context, exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, None, "error", elapsed, str(exc),
        )
        await _broadcast_progress("llm_error", f"LLM error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        return {"news_risks": [], "news_opportunities": []}


# ---------------------------------------------------------------------------
# Graph definition — parallel fetch → merge → build → LLM
# ---------------------------------------------------------------------------

_builder = StateGraph(NewsAgentState)

# Parallel fetch nodes (fan-out from START)
_builder.add_node("fetch_newsapi", _fetch_newsapi_node)
_builder.add_node("fetch_gdelt", _fetch_gdelt_node)

# Fan-in merge then existing pipeline
_builder.add_node("merge_news", _merge_news_node)
_builder.add_node("build_items", _build_news_items_node)
_builder.add_node("news_risk_llm", _news_risk_llm_node)

# Fan-out: START → both fetch nodes in parallel
_builder.add_edge(START, "fetch_newsapi")
_builder.add_edge(START, "fetch_gdelt")

# Fan-in: both fetch nodes → merge
_builder.add_edge("fetch_newsapi", "merge_news")
_builder.add_edge("fetch_gdelt", "merge_news")

# Linear pipeline after merge
_builder.add_edge("merge_news", "build_items")
_builder.add_edge("build_items", "news_risk_llm")
_builder.add_edge("news_risk_llm", END)

NEWS_GRAPH = _builder.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _resolve_entity_data(
    scope: OemScope,
) -> tuple[EntityData | None, EntityData | None]:
    """Fetch OEM and supplier details from the DB using IDs in scope."""
    db = SessionLocal()
    try:
        oem_data: EntityData | None = None
        supplier_data: EntityData | None = None

        oem_id_str = scope.get("oemId")
        if oem_id_str:
            oem = get_oem_by_id(db, UUID(oem_id_str))
            if oem:
                oem_data = _entity_from_model(oem)

        supplier_id_str = scope.get("supplierId")
        if supplier_id_str:
            supplier = get_supplier_by_id(db, UUID(supplier_id_str))
            if supplier:
                supplier_data = _entity_from_model(supplier)

        return oem_data, supplier_data
    finally:
        db.close()


async def run_news_agent_graph(
    news_data: dict[str, list[dict]],
    scope: OemScope,
    context: Literal["supplier", "global"],
) -> dict[str, list[dict]]:
    """
    Orchestrate the News Agent using LangGraph and LangChain.

    Fetches from NewsAPI and GDELT in parallel, merges and deduplicates the
    articles, then runs LLM risk/opportunity extraction.

    OEM and supplier details are fetched from the database using ``oemId``
    and ``supplierId`` from the scope.
    """
    oem_data, supplier_data = _resolve_entity_data(scope)

    oem_label = (oem_data or {}).get("name") or scope.get("oemName") or "unknown"
    sup_label = (supplier_data or {}).get("name") if supplier_data else None
    entity_label = f"{oem_label}/{sup_label}" if sup_label else oem_label

    logger.info("[NewsAgent:%s] Starting news graph for %s", context, entity_label)
    await _broadcast_progress(
        "started", f"Starting {context} news analysis for {entity_label}",
        context, {"oem": oem_label, "supplier": sup_label},
        oem_name=oem_label, supplier_name=sup_label,
    )

    initial_state: NewsAgentState = {
        "scope": scope,
        "news_data": news_data,
        "context": context,
        "oem_data": oem_data,
        "supplier_data": supplier_data,
    }

    final_state = await NEWS_GRAPH.ainvoke(initial_state)

    risks = final_state.get("news_risks") or []
    opps = final_state.get("news_opportunities") or []

    risks_for_db: list[dict] = []
    opps_for_db: list[dict] = []

    for r in risks:
        db_risk = {
            "title": r["title"],
            "description": r["description"],
            "severity": r.get("severity"),
            "affectedRegion": r.get("affectedRegion"),
            "affectedSupplier": r.get("affectedSupplier"),
            "estimatedImpact": r.get("estimatedImpact"),
            "estimatedCost": r.get("estimatedCost"),
            "sourceType": "news",
            "sourceData": {
                "risk_type": r.get("risk_type"),
                "source": r.get("source"),
                "context": context,
            },
        }
        risks_for_db.append(db_risk)

    for o in opps:
        db_opp = {
            "title": o["title"],
            "description": o["description"],
            "type": o.get("type"),
            "affectedRegion": o.get("affectedRegion"),
            "potentialBenefit": o.get("potentialBenefit"),
            "estimatedValue": o.get("estimatedValue"),
            "sourceType": "news",
            "sourceData": {"context": context},
        }
        opps_for_db.append(db_opp)

    logger.info(
        "[NewsAgent:%s] Completed: risks=%d opportunities=%d for %s",
        context, len(risks_for_db), len(opps_for_db), entity_label,
    )
    await _broadcast_progress(
        "context_done",
        f"Completed {context} analysis: {len(risks_for_db)} risks, {len(opps_for_db)} opportunities",
        context,
        {"risks": len(risks_for_db), "opportunities": len(opps_for_db)},
        oem_name=oem_label, supplier_name=sup_label,
    )

    return {
        "risks": risks_for_db,
        "opportunities": opps_for_db,
        "newsapi_raw": final_state.get("newsapi_raw") or [],
        "gdelt_raw": final_state.get("gdelt_raw") or [],
        "news_items": [dict(item) for item in (final_state.get("news_items") or [])],
    }
