import json
import logging
from typing import TypedDict, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.services.langchain_llm import get_chat_model
from app.services.agent_orchestrator import _extract_json
from app.services.agent_types import OemScope

logger = logging.getLogger(__name__)


class WeatherItem(TypedDict):
    city: str
    country: str
    temperature: float | int | None
    condition: str
    description: str
    humidity: int | None
    windSpeed: float | int | None
    visibility: int | None


class WeatherAgentState(TypedDict, total=False):
    scope: OemScope
    weather_data: dict[str, list[dict]]
    weather_items: list[WeatherItem]
    weather_risks: list[dict]
    weather_opportunities: list[dict]


def _build_weather_items_node(state: WeatherAgentState) -> WeatherAgentState:
    """
    Normalize raw weather data into WeatherItem structures.
    """
    raw = state.get("weather_data") or {}
    items = raw.get("weather") or []

    normalized: list[WeatherItem] = []
    for item in items:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        normalized.append(
            {
                "city": str(data.get("city") or ""),
                "country": str(data.get("country") or ""),
                "temperature": data.get("temperature"),
                "condition": str(data.get("condition") or ""),
                "description": str(data.get("description") or ""),
                "humidity": data.get("humidity"),
                "windSpeed": data.get("windSpeed"),
                "visibility": data.get("visibility"),
            }
        )

    return {"weather_items": normalized}


_prompt: ChatPromptTemplate | None = None


def _get_langchain_chain() -> Any | None:
    """
    Build a LangChain chain for weather exposure analysis.
    Uses Anthropic or Ollama per settings.llm_provider (see langchain_llm.get_chat_model).
    """
    global _prompt

    llm = get_chat_model()
    if llm is None:
        return None

    if _prompt is None:
        _prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a Weather Agent for a manufacturing "
                        "supply chain. You receive normalized weather "
                        "data for shipment routes and must produce "
                        "structured weather risk pointers and potential "
                        "opportunities. Focus on:\n"
                        "- weather_exposure_score\n"
                        "- storm_risk\n"
                        "- temperature_extreme_days\n\n"
                        "Return ONLY valid JSON, no commentary."
                    ),
                ),
                (
                    "user",
                    (
                        "Analyze the following per-city weather data for "
                        "supply chain weather risks and opportunities.\n\n"
                        "Weather JSON:\n{weather_items_json}\n\n"
                        "Return JSON of shape:\n"
                        "{{\n"
                        '  "risks": [\n'
                        "    {{\n"
                        '      "title": str,\n'
                        '      "description": str,\n'
                        '      "severity": "low" | "medium" | "high" '
                        '| "critical",\n'
                        '      "affectedRegion": str | null,\n'
                        '      "affectedSupplier": str | null,\n'
                        '      "estimatedImpact": str | null,\n'
                        '      "estimatedCost": number | null,\n'
                        '      "weather_exposure_score": number | null,\n'
                        '      "storm_risk": number | null,\n'
                        '      "temperature_extreme_days": number | null\n'
                        "    }}\n"
                        "  ],\n"
                        '  "opportunities": [\n'
                        "    {{\n"
                        '      "title": str,\n'
                        '      "description": str,\n'
                        '      "type": "cost_saving" | "time_saving" '
                        '| "quality_improvement" | "market_expansion" '
                        '| "supplier_diversification",\n'
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

    return _prompt | llm


def _heuristic_weather_from_items(
    items: list[WeatherItem],
) -> tuple[list[dict], list[dict]]:
    """
    Simple deterministic fallback when LLM is not configured.
    """
    risks: list[dict] = []
    opps: list[dict] = []

    for item in items:
        city = item["city"] or "Unknown city"
        temp = item.get("temperature") or 0
        condition = (item.get("condition") or "").lower()

        exposure = 0
        storm_risk = 0
        extreme_days = 0

        if condition in {"storm", "rain"}:
            exposure += 40
            storm_risk = 70 if condition == "storm" else 40
        if temp <= 0 or temp >= 35:
            exposure += 30
            extreme_days = 2

        if exposure >= 40:
            risks.append(
                {
                    "title": f"Weather risk for {city}",
                    "description": (
                        f"Adverse weather in {city} with condition "
                        f"{item.get('condition')} and temperature {temp}°C."
                    ),
                    "severity": "high" if exposure >= 70 else "medium",
                    "affectedRegion": city,
                    "affectedSupplier": None,
                    "estimatedImpact": (
                        "Potential delays due to local weather conditions."
                    ),
                    "estimatedCost": None,
                    "weather_exposure_score": exposure,
                    "storm_risk": storm_risk,
                    "temperature_extreme_days": extreme_days,
                }
            )
        else:
            opps.append(
                {
                    "title": f"Stable weather window in {city}",
                    "description": (
                        f"Weather in {city} appears stable for planned "
                        f"shipments with condition {item.get('condition')}."
                    ),
                    "type": "time_saving",
                    "affectedRegion": city,
                    "potentialBenefit": (
                        "Opportunity to prioritize shipments through this "
                        "location while conditions are favorable."
                    ),
                    "estimatedValue": None,
                }
            )

    return risks, opps


async def _weather_risk_llm_node(
    state: WeatherAgentState,
) -> WeatherAgentState:
    """
    Convert WeatherItem list into risks and opportunities using LangChain.
    Falls back to simple heuristics when Anthropic is not configured.
    """
    items = state.get("weather_items") or []
    if not items:
        return {"weather_risks": [], "weather_opportunities": []}

    chain = _get_langchain_chain()
    if not chain:
        risks, opps = _heuristic_weather_from_items(items)
        return {"weather_risks": risks, "weather_opportunities": opps}

    try:
        items_json = json.dumps(items, indent=2)
        msg = await chain.ainvoke({"weather_items_json": items_json})

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

        return {"weather_risks": risks, "weather_opportunities": opps}
    except Exception as exc:
        logger.exception("WeatherAgent LLM error: %s", exc)
        risks, opps = _heuristic_weather_from_items(items)
        return {"weather_risks": risks, "weather_opportunities": opps}


_builder = StateGraph(WeatherAgentState)
_builder.add_node("build_items", _build_weather_items_node)
_builder.add_node("weather_risk_llm", _weather_risk_llm_node)
_builder.set_entry_point("build_items")
_builder.add_edge("build_items", "weather_risk_llm")
_builder.add_edge("weather_risk_llm", END)

WEATHER_GRAPH = _builder.compile()


async def run_weather_agent_graph(
    weather_data: dict[str, list[dict]],
    scope: OemScope,
) -> dict[str, list[dict]]:
    """
    Orchestrate the Weather Agent using LangGraph and LangChain.
    """
    initial_state: WeatherAgentState = {
        "scope": scope,
        "weather_data": weather_data,
    }

    final_state = await WEATHER_GRAPH.ainvoke(initial_state)

    risks = final_state.get("weather_risks") or []
    opps = final_state.get("weather_opportunities") or []

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
            "sourceType": "weather",
            "sourceData": {
                "weatherExposure": {
                    "weather_exposure_score": r.get("weather_exposure_score"),
                    "storm_risk": r.get("storm_risk"),
                    "temperature_extreme_days": r.get("temperature_extreme_days"),
                }
            },
        }
        risks_for_db.append(db_risk)

    for o in opps:
        db_opp = {
            "title": o["title"],
            "description": o["description"],
            "type": o.get("type", "time_saving"),
            "affectedRegion": o.get("affectedRegion"),
            "potentialBenefit": o.get("potentialBenefit"),
            "estimatedValue": o.get("estimatedValue"),
            "sourceType": "weather",
            "sourceData": None,
        }
        opps_for_db.append(db_opp)

    return {"risks": risks_for_db, "opportunities": opps_for_db}
