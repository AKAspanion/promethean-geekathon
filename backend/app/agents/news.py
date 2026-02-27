import json
import logging
from typing import TypedDict, Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model
from app.services.agent_types import OemScope

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
    news_data: dict[str, list[dict]]
    news_items: list[NewsItem]
    news_risks: list[dict]
    news_opportunities: list[dict]


def _build_news_items_node(state: NewsAgentState) -> NewsAgentState:
    """
    Normalize raw news data into NewsItem structures.
    """
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
    """Return LangChain chat model (Anthropic or Ollama per settings)."""
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
    Returns empty lists when Anthropic is not configured.
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


_builder = StateGraph(NewsAgentState)
_builder.add_node("build_items", _build_news_items_node)
_builder.add_node("news_risk_llm", _news_risk_llm_node)
_builder.set_entry_point("build_items")
_builder.add_edge("build_items", "news_risk_llm")
_builder.add_edge("news_risk_llm", END)

NEWS_GRAPH = _builder.compile()


async def run_news_agent_graph(
    news_data: dict[str, list[dict]],
    scope: OemScope,
    context: Literal["supplier", "global"],
) -> dict[str, list[dict]]:
    """
    Orchestrate the News Agent using LangGraph and LangChain.
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
