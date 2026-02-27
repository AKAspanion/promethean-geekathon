from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama

from app.config import settings
from app.core.risk_engine import compute_risk
from app.schemas.weather_agent import RiskLevel
from app.services.weather_service import get_current_weather

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    city: str
    weather_data: dict[str, Any] | None
    risk_dict: dict[str, Any] | None


_weather_store: dict[str, Any] = {}
_risk_store: dict[str, Any] = {}
_weather_fetch_lock = asyncio.Lock()


def _weather_summary(data: dict[str, Any]) -> str:
    loc = data.get("location") or {}
    current = data.get("current") or {}
    cond = (current.get("condition") or {}).get("text", "Unknown")
    return f"Weather at {loc.get('name', 'Unknown')} ({loc.get('country', '')}): {cond}, temp {current.get('temp_c')}°C, wind {current.get('wind_kph')} km/h, precip {current.get('precip_mm')} mm, visibility {current.get('vis_km')} km."


@tool
async def get_weather(city: str) -> str:
    """Fetch current weather for a location. Call this first with the city name (e.g. New Delhi, London)."""
    city = (city or "").strip()
    if not city:
        return "Error: city is required."
    if city in _weather_store:
        return _weather_summary(_weather_store[city])
    async with _weather_fetch_lock:
        if city in _weather_store:
            return _weather_summary(_weather_store[city])
        data = await get_current_weather(city)
        if not data:
            return "Error: Could not fetch weather for this location."
        _weather_store[city] = data
    return _weather_summary(data)


def _risk_brief(risk_dict: dict[str, Any]) -> str:
    level = risk_dict.get("overall_level", RiskLevel.LOW)
    score = risk_dict.get("overall_score", 0)
    concerns = risk_dict.get("primary_concerns") or []
    actions = risk_dict.get("suggested_actions") or []
    return f"Supply chain risk: {level.value if hasattr(level, 'value') else level} (score {score}/100). Concerns: {'; '.join(concerns[:2])}. Actions: {'; '.join(actions[:2])}."


@tool
def compute_supply_chain_risk(weather_key: str) -> str:
    """Compute supply chain risk from the weather already fetched. Pass the key as the city name (e.g. New Delhi). Call after get_weather."""
    if weather_key in _risk_store:
        return _risk_brief(_risk_store[weather_key])
    data = _weather_store.get(weather_key)
    if not data:
        return "Error: No weather data found. Call get_weather first."
    current = data.get("current") or data
    risk_dict = compute_risk({"current": current})
    factors = risk_dict.get("factors") or []
    _risk_store[weather_key] = {
        **risk_dict,
        "factors": [f.model_dump() if hasattr(f, "model_dump") else f for f in factors],
    }
    return _risk_brief(_risk_store[weather_key])


TOOLS = [get_weather, compute_supply_chain_risk]

_llm_with_tools = None


def _get_llm():
    global _llm_with_tools
    if _llm_with_tools is None:
        _llm_with_tools = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.3,
            num_predict=512,
        ).bind_tools(TOOLS)
    return _llm_with_tools


async def _agent_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages") or []
    if not messages:
        return {"messages": []}
    try:
        llm = _get_llm()
        response = await llm.ainvoke(messages)
        return {"messages": [response]}
    except Exception as e:
        logger.warning("Agent LLM call failed, flow may use fallback: %s", e)
        return {"messages": [AIMessage(content="", tool_calls=[])]}


def _should_continue(state: AgentState) -> Literal["tools", "fallback_tools", "end"]:
    messages = state.get("messages") or []
    if not messages:
        return "end"
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return "end"
    if last.tool_calls:
        return "tools"
    city = (state.get("city") or "").strip()
    key = city or None
    if key and (
        state.get("weather_data") is not None and state.get("risk_dict") is not None
    ):
        return "end"
    if key and not last.tool_calls:
        return "fallback_tools"
    return "end"


async def _tools_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": []}
    tool_node = ToolNode(TOOLS)
    result = await tool_node.ainvoke(state)
    city = (state.get("city") or "").strip()
    key = city or None
    updates: dict[str, Any] = {"messages": result.get("messages", [])}
    if key and key in _weather_store:
        updates["weather_data"] = _weather_store[key]
    if key and key in _risk_store:
        updates["risk_dict"] = _risk_store[key]
    return updates


async def _fallback_tools_node(state: AgentState) -> dict[str, Any]:
    """Run when the model did not call tools; fetches weather and risk and injects as tool results so the agent can summarize."""
    city = (state.get("city") or "").strip()
    if not city:
        return {"messages": []}
    data = await get_current_weather(city)
    if not data:
        return {"weather_data": None, "risk_dict": None, "messages": []}
    _weather_store[city] = data
    current = data.get("current") or data
    risk_dict = compute_risk({"current": current})
    factors = risk_dict.get("factors") or []
    risk_dict_serializable = {
        **risk_dict,
        "factors": [f.model_dump() if hasattr(f, "model_dump") else f for f in factors],
    }
    _risk_store[city] = risk_dict_serializable
    loc = data.get("location") or {}
    current_cond = (current.get("condition") or {}).get("text", "Unknown")
    weather_brief = f"Weather at {loc.get('name', 'Unknown')}: {current_cond}, temp {current.get('temp_c')}°C, wind {current.get('wind_kph')} km/h."
    risk_brief = f"Risk: {risk_dict.get('overall_level', RiskLevel.LOW)} (score {risk_dict.get('overall_score', 0)}/100)."
    tool_messages = [
        ToolMessage(content=weather_brief, tool_call_id="fallback_weather"),
        ToolMessage(content=risk_brief, tool_call_id="fallback_risk"),
    ]
    return {
        "weather_data": data,
        "risk_dict": risk_dict_serializable,
        "messages": tool_messages,
    }


def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", _tools_node)
    builder.add_node("fallback_tools", _fallback_tools_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", "fallback_tools": "fallback_tools", "end": END},
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("fallback_tools", "agent")
    return builder


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph().compile()
    return _graph


def _build_summary_prompt(
    weather_data: dict[str, Any], risk_dict: dict[str, Any]
) -> str:
    loc = (weather_data or {}).get("location") or {}
    current = (weather_data or {}).get("current") or {}
    factors = risk_dict.get("factors") or []
    factors_text = "\n".join(
        f"- {f.get('factor', '')}: {f.get('level', '')} (score {f.get('score', 0)}): {f.get('summary', '')}"
        for f in factors
    )
    return f"""Location: {loc.get("name", "Unknown")} ({loc.get("region", "")}, {loc.get("country", "")})
Current weather: {(current.get("condition") or {}).get("text", "Unknown")}, temp {current.get("temp_c")}°C, wind {current.get("wind_kph")} km/h.
Overall risk: {risk_dict.get("overall_level", "unknown")} (score {risk_dict.get("overall_score", 0)}/100).
Primary concerns: {chr(10).join(risk_dict.get("primary_concerns") or [])}
Suggested actions: {chr(10).join(risk_dict.get("suggested_actions") or [])}
Risk factors:
{factors_text}
Write a short executive summary (2-4 sentences) for a manufacturing operations manager: main weather-driven risks and top 2-3 mitigation actions. Be concise and actionable."""


SYSTEM_PROMPT = """You are a supply chain risk analyst for manufacturing. Given a city:
1. Call get_weather with that city (only once).
2. Call compute_supply_chain_risk with the key as the city name (only once).
3. Then write a short executive summary (2-4 sentences) for an operations manager. Base your summary only on the tool results above; state the main weather-driven risks and top 2-3 mitigation actions. Be concise and do not invent risks not stated in the tool output."""


async def run_weather_risk_agent(city: str) -> dict[str, Any]:
    city = city.strip()
    _weather_store.pop(city, None)
    _risk_store.pop(city, None)

    initial: AgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Assess supply chain weather risk for city {city}. Use your tools to get weather and risk, then provide your executive summary."
            ),
        ],
        "city": city,
    }

    graph = _get_graph()
    final = await graph.ainvoke(initial)

    messages = final.get("messages") or []
    weather_data = final.get("weather_data")
    risk_dict = final.get("risk_dict")

    if not weather_data and city in _weather_store:
        weather_data = _weather_store.get(city)
    if not risk_dict and city in _risk_store:
        risk_dict = _risk_store.get(city)

    llm_summary = None
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not m.tool_calls:
            llm_summary = (m.content or "").strip() or None
            break

    if not llm_summary and weather_data and risk_dict:
        try:
            llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0.3,
                num_predict=400,
            )
            prompt = _build_summary_prompt(weather_data, risk_dict)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            llm_summary = (
                response.content
                if hasattr(response, "content")
                else str(response) or ""
            ).strip() or None
        except Exception as e:
            logger.warning("Ollama summary fallback failed: %s", e)

    return {
        "weather_data": weather_data,
        "risk_dict": risk_dict,
        "llm_summary": llm_summary,
    }
