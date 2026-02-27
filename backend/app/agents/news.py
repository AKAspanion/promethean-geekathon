import json
import logging
from typing import TypedDict, Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START

from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model
from app.services.agent_types import OemScope
from app.data.news import NewsDataSource
from app.data.gdelt import GDELTDataSource

logger = logging.getLogger(__name__)


class NewsItem(TypedDict):
    title: str | None
    description: str | None
    url: str | None
    source: str | None
    publishedAt: str | None
    author: str | None
    content: str | None


class NewsAgentState(TypedDict, total=False):
    scope: OemScope
    context: Literal["supplier", "global"]
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
# Keyword helpers
# ---------------------------------------------------------------------------

def _newsapi_keywords(scope: OemScope | None) -> list[str]:
    base = ["supply chain", "manufacturing", "logistics", "shipping"]
    if scope:
        # Supplier names — most targeted signal
        for name in (scope.get("supplierNames") or [])[:3]:
            base.append(name)
        # Commodities traded by the suppliers
        for commodity in (scope.get("commodities") or [])[:3]:
            base.append(f"{commodity} supply chain")
        # Cities / countries where suppliers operate
        for city in (scope.get("cities") or [])[:2]:
            base.append(f"supply chain {city}")
        for country in (scope.get("countries") or [])[:2]:
            base.append(f"supply chain {country}")
    return base


def _gdelt_keywords(scope: OemScope | None) -> list[str]:
    base = [
        "supply chain disruption",
        "trade sanctions",
        "port strike",
        "factory shutdown",
        "natural disaster manufacturing",
    ]
    if scope:
        # Supplier-specific geopolitical signals
        for name in (scope.get("supplierNames") or [])[:2]:
            base.append(f"{name} disruption")
        for commodity in (scope.get("commodities") or [])[:2]:
            base.append(f"{commodity} shortage")
        for country in (scope.get("countries") or [])[:2]:
            base.append(f"sanctions {country}")
    return base


# ---------------------------------------------------------------------------
# Parallel fetch nodes
# ---------------------------------------------------------------------------

async def _fetch_newsapi_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch articles from NewsAPI.org."""
    scope = state.get("scope")
    keywords = _newsapi_keywords(scope)
    try:
        source = NewsDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("fetch_newsapi_node: fetched %d articles", len(raw))
    except Exception as exc:
        logger.exception("fetch_newsapi_node error: %s", exc)
        raw = []
    return {"newsapi_raw": raw}


async def _fetch_gdelt_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch geopolitical event articles from GDELT (no API key required)."""
    scope = state.get("scope")
    keywords = _gdelt_keywords(scope)
    try:
        source = GDELTDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("fetch_gdelt_node: fetched %d articles", len(raw))
    except Exception as exc:
        logger.exception("fetch_gdelt_node error: %s", exc)
        raw = []
    return {"gdelt_raw": raw}


# ---------------------------------------------------------------------------
# Merge node — fan-in after parallel fetches
# ---------------------------------------------------------------------------

def _merge_news_node(state: NewsAgentState) -> NewsAgentState:
    """
    Combine articles from all 3 sources + any pre-fetched news_data.
    Deduplicates by normalised title to avoid redundant LLM tokens.
    """
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
        "_merge_news_node: %d total → %d unique articles after dedup",
        len(combined),
        len(unique),
    )
    # Store as a news_data dict so _build_news_items_node can consume it normally
    return {"news_data": {"news": unique}}


# ---------------------------------------------------------------------------
# Existing nodes (unchanged logic)
# ---------------------------------------------------------------------------

def _build_news_items_node(state: NewsAgentState) -> NewsAgentState:
    """Normalize raw news data into NewsItem structures."""
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
    return {"news_items": normalized}


_prompt_supplier: ChatPromptTemplate | None = None
_prompt_global: ChatPromptTemplate | None = None


def _get_llm():
    return get_chat_model()


def _get_prompt(context: Literal["supplier", "global"]) -> ChatPromptTemplate:
    global _prompt_supplier, _prompt_global

    if context == "supplier":
        if _prompt_supplier is None:
            _prompt_supplier = ChatPromptTemplate.from_messages(
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
                            "of the OEM and suppliers.\n\n"
                            "News JSON:\n{news_items_json}\n\n"
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
        return _prompt_supplier

    if _prompt_global is None:
        _prompt_global = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a global supply chain News Agent. You "
                        "receive news about macro events (geopolitics, "
                        "trade, climate, logistics). Extract only "
                        "material global supply chain risks."
                    ),
                ),
                (
                    "user",
                    (
                        "Analyze the following news items for global supply "
                        "chain risk (not just a single OEM).\n\n"
                        "News JSON:\n{news_items_json}\n\n"
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
    return _prompt_global


async def _news_risk_llm_node(state: NewsAgentState) -> NewsAgentState:
    """
    Convert NewsItem list into risks and opportunities using LangChain.
    Returns empty lists when LLM is not configured.
    """
    items = state.get("news_items") or []
    if not items:
        return {"news_risks": [], "news_opportunities": []}

    llm = _get_llm()
    if not llm:
        return {"news_risks": [], "news_opportunities": []}

    context = state.get("context", "supplier") or "supplier"
    prompt = _get_prompt(context)  # type: ignore[arg-type]
    chain = prompt | llm

    try:
        items_json = json.dumps(items, indent=2)
        msg = await chain.ainvoke({"news_items_json": items_json})

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

        return {"news_risks": risks, "news_opportunities": opps}
    except Exception as exc:
        logger.exception("NewsAgent LLM error: %s", exc)
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
# Public entrypoint (signature unchanged — backward compatible)
# ---------------------------------------------------------------------------

async def run_news_agent_graph(
    news_data: dict[str, list[dict]],
    scope: OemScope,
    context: Literal["supplier", "global"],
) -> dict[str, list[dict]]:
    """
    Orchestrate the News Agent using LangGraph and LangChain.

    Fetches from NewsAPI, GDELT, and Finlight in parallel, merges and
    deduplicates the articles, then runs LLM risk/opportunity extraction.
    `news_data` (pre-fetched externally) is merged in as well for backward
    compatibility.
    """
    initial_state: NewsAgentState = {
        "scope": scope,
        "news_data": news_data,
        "context": context,
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
            "severity": r.get("severity", "medium"),
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
            "type": o.get("type", "cost_saving"),
            "affectedRegion": o.get("affectedRegion"),
            "potentialBenefit": o.get("potentialBenefit"),
            "estimatedValue": o.get("estimatedValue"),
            "sourceType": "news",
            "sourceData": {"context": context},
        }
        opps_for_db.append(db_opp)

    return {"risks": risks_for_db, "opportunities": opps_for_db}
