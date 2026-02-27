import json
import logging
from datetime import datetime
from typing import TypedDict, Any

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.services.agent_orchestrator import _extract_json
from app.services.agent_types import OemScope
from app.services.langchain_llm import get_chat_model

logger = logging.getLogger(__name__)


class ShipmentTimelineEntry(TypedDict):
    day: int
    date: str
    estimated_location: str
    milestone: str
    status: str  # "moved" | "no_movement"


class ShipmentMetadata(TypedDict):
    route: str
    origin: str
    destination: str
    status: str
    delayDays: int
    disruptionReason: str | None
    plannedTransitDays: int
    actualTransitDays: int
    daysWithoutMovement: int
    timeline: list[ShipmentTimelineEntry]


class ShipmentAgentState(TypedDict, total=False):
    scope: OemScope
    shipping_data: dict[str, list[dict]]
    shipment_metadata: list[ShipmentMetadata]
    shipping_risks: list[dict]


def _build_shipment_metadata_node(state: ShipmentAgentState) -> ShipmentAgentState:
    """
    Normalize raw shipping data into structured ShipmentMetadata suitable for
    analysis by the Shipment Agent.
    """
    raw_shipping = state.get("shipping_data") or {}
    shipping_items = raw_shipping.get("shipping") or []

    metadata_list: list[ShipmentMetadata] = []

    for item in shipping_items:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue

        timeline = data.get("timeline") or []
        # Ensure timeline entries have required keys; drop obviously bad rows.
        cleaned_timeline: list[ShipmentTimelineEntry] = []
        for entry in timeline:
            if not isinstance(entry, dict):
                continue
            try:
                day = int(entry.get("day", 0))
            except (TypeError, ValueError):
                continue
            if day <= 0:
                continue
            date_str = str(entry.get("date") or "")
            try:
                # Best-effort validation; do not raise on failure.
                if date_str:
                    datetime.fromisoformat(date_str)
            except ValueError:
                date_str = ""

            cleaned_timeline.append(
                {
                    "day": day,
                    "date": date_str,
                    "estimated_location": str(entry.get("estimated_location") or ""),
                    "milestone": str(entry.get("milestone") or "in_transit"),
                    "status": str(entry.get("status") or "moved"),
                }
            )

        meta: ShipmentMetadata = {
            "route": str(data.get("route") or "unknown"),
            "origin": str(data.get("origin") or ""),
            "destination": str(data.get("destination") or ""),
            "status": str(data.get("status") or "normal"),
            "delayDays": int(data.get("delayDays") or 0),
            "disruptionReason": data.get("disruptionReason"),
            "plannedTransitDays": int(data.get("plannedTransitDays") or 0),
            "actualTransitDays": int(data.get("actualTransitDays") or 0),
            "daysWithoutMovement": int(data.get("daysWithoutMovement") or 0),
            "timeline": cleaned_timeline,
        }
        metadata_list.append(meta)

    return {"shipment_metadata": metadata_list}


_prompt: ChatPromptTemplate | None = None


def _get_langchain_chain() -> Any | None:
    """
    Build a LangChain chain for shipment risk extraction.
    Uses Anthropic or Ollama per settings.llm_provider (see langchain_llm.get_chat_model).
    Returns None when no LLM is configured so callers fall back to heuristic logic.
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
                        "You are a Shipment Agent for a manufacturing supply chain. "
                        "You receive normalized shipment timelines and metrics and "
                        "must produce structured shipment risk pointers, focused on:\n"
                        "- delay_risk (milestone vs actual delays)\n"
                        "- stagnation_risk (no movement for X days)\n"
                        "- velocity_risk (too slow/fast vs expected transit days)\n\n"
                        "Return ONLY valid JSON, no additional commentary."
                    ),
                ),
                (
                    "user",
                    (
                        "Analyze the following shipment metadata for risks.\n\n"
                        "Metadata JSON:\n{shipment_metadata_json}\n\n"
                        "Return JSON of shape:\n"
                        "{{\n"
                        '  "risks": [\n'
                        "    {{\n"
                        '      "title": str,\n'
                        '      "description": str,\n'
                        '      "severity": '
                        '"low" | "medium" | "high" | "critical",\n'
                        '      "affectedRegion": str | null,\n'
                        '      "affectedSupplier": str | null,\n'
                        '      "estimatedImpact": str | null,\n'
                        '      "estimatedCost": number | null,\n'
                        '      "route": str,\n'
                        '      "delay_risk": {{ "score": number, '
                        '"label": "low|medium|high|critical" }},\n'
                        '      "stagnation_risk": {{ "score": number, '
                        '"label": "low|medium|high|critical" }},\n'
                        '      "velocity_risk": {{ "score": number, '
                        '"label": "low|medium|high|critical" }}\n'
                        "    }}\n"
                        "  ]\n"
                        "}}\n"
                        'If no risks, return {{"risks": []}}.'
                    ),
                ),
            ]
        )

    return _prompt | llm


def _band(score: int) -> str:
    if score <= 25:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


def _heuristic_shipping_risks_from_metadata(
    metadata_list: list[ShipmentMetadata],
) -> list[dict]:
    """
    Deterministic heuristic fallback for shipment risks when Anthropic is not
    configured or LLM calls fail.
    """
    risks: list[dict] = []

    for meta in metadata_list:
        if meta["status"] == "normal" and not meta["delayDays"]:
            continue

        delay = meta["delayDays"]
        stagnation = meta["daysWithoutMovement"]
        planned = meta["plannedTransitDays"] or 1
        actual = meta["actualTransitDays"] or planned
        velocity_ratio = actual / planned if planned else 1.0

        delay_score = min(100, delay * 10)
        stagnation_score = min(100, stagnation * 15)
        velocity_score = min(100, int(abs(velocity_ratio - 1.0) * 40))

        combined_score = max(delay_score, stagnation_score, velocity_score)
        severity_label = _band(int(combined_score))

        risks.append(
            {
                "title": f"Shipment risk on route {meta['route']}",
                "description": (
                    f"Route {meta['route']} shows a delay of {delay} days and "
                    f"{stagnation} days without movement. Planned transit "
                    f"{planned} days vs actual {actual} days."
                ),
                "severity": severity_label,
                "affectedRegion": None,
                "affectedSupplier": None,
                "estimatedImpact": (
                    "Potential shipment delay impacting OEM deliveries."
                ),
                "estimatedCost": None,
                "route": meta["route"],
                "delay_risk": {
                    "score": delay_score,
                    "label": _band(delay_score),
                },
                "stagnation_risk": {
                    "score": stagnation_score,
                    "label": _band(stagnation_score),
                },
                "velocity_risk": {
                    "score": velocity_score,
                    "label": _band(velocity_score),
                },
            }
        )

    return risks


def _normalize_supplier_labels(raw: Any) -> list[str]:
    """
    Normalize supplier labels coming from LLM or upstream data into a
    deduplicated list of non-empty strings.
    """
    names: list[str] = []
    if isinstance(raw, (list, tuple)):
        candidates = raw
    elif raw:
        candidates = [raw]
    else:
        candidates = []

    for value in candidates:
        label = str(value).strip()
        if not label:
            continue
        names.append(label)

    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return unique


def _infer_suppliers_for_route(
    scope: OemScope, meta: ShipmentMetadata | None
) -> list[str]:
    """
    Best-effort inference of affected suppliers for a shipment route based on
    the OEM scope. We match known supplier names against the route, origin, and
    destination fields.
    """
    if not meta:
        return []

    supplier_names = scope.get("supplierNames") or []
    if not supplier_names:
        return []

    origin = str(meta.get("origin") or "").lower()
    destination = str(meta.get("destination") or "").lower()
    route = str(meta.get("route") or "").lower()

    inferred: list[str] = []
    seen: set[str] = set()

    for raw_name in supplier_names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        key = name.lower()
        # Match by equality, prefix, or substring against origin/destination/route.
        if not (
            origin == key
            or destination == key
            or origin.startswith(key)
            or destination.startswith(key)
            or (key and key in route)
        ):
            continue
        if key in seen:
            continue
        seen.add(key)
        inferred.append(name)

    return inferred


async def _shipment_risk_llm_node(state: ShipmentAgentState) -> ShipmentAgentState:
    """
    LangChain-powered node that converts ShipmentMetadata into shipping risks.
    Falls back to deterministic heuristics if Anthropic is not configured.
    """
    metadata_list = state.get("shipment_metadata") or []
    if not metadata_list:
        return {"shipping_risks": []}

    chain = _get_langchain_chain()
    if not chain:
        return {
            "shipping_risks": _heuristic_shipping_risks_from_metadata(metadata_list)
        }

    try:
        metadata_json = json.dumps(metadata_list, indent=2)
        msg = await chain.ainvoke({"shipment_metadata_json": metadata_json})

        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            pieces: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    pieces.append(str(block.get("text") or ""))
                else:
                    pieces.append(str(block))
            raw_text = "".join(pieces)

        parsed = _extract_json(raw_text) or {}
        raw_risks = parsed.get("risks") or []

        normalized_risks: list[dict] = []
        for risk in raw_risks:
            if not isinstance(risk, dict):
                continue
            title = (str(risk.get("title") or "")).strip()
            desc = (str(risk.get("description") or "")).strip()
            if not title or not desc:
                continue
            normalized_risks.append(risk)

        return {"shipping_risks": normalized_risks}
    except Exception as exc:
        logger.exception("ShipmentAgent LLM error: %s", exc)
        return {
            "shipping_risks": _heuristic_shipping_risks_from_metadata(metadata_list)
        }


_builder = StateGraph(ShipmentAgentState)
_builder.add_node("build_metadata", _build_shipment_metadata_node)
_builder.add_node("shipment_risk_llm", _shipment_risk_llm_node)
_builder.set_entry_point("build_metadata")
_builder.add_edge("build_metadata", "shipment_risk_llm")
_builder.add_edge("shipment_risk_llm", END)

SHIPMENT_GRAPH = _builder.compile()


async def run_shipment_agent_graph(
    shipping_data: dict[str, list[dict]],
    scope: OemScope,
) -> dict[str, list[dict]]:
    """
    Orchestrate the Shipment Agent using LangGraph and LangChain.

    Returns:
        {
          "risks": [ risk_dicts ready for create_risk_from_dict ]
        }
    """
    initial_state: ShipmentAgentState = {
        "scope": scope,
        "shipping_data": shipping_data,
    }

    final_state = await SHIPMENT_GRAPH.ainvoke(initial_state)

    metadata_list = final_state.get("shipment_metadata") or []
    shipping_risks = final_state.get("shipping_risks") or []

    metadata_by_route: dict[str, ShipmentMetadata] = {
        meta["route"]: meta for meta in metadata_list
    }

    risks_for_db: list[dict] = []

    for risk in shipping_risks:
        route = str(risk.get("route") or "")
        meta = metadata_by_route.get(route)

        source_data: dict[str, Any] = {
            "shipmentMetadata": meta,
            "riskMetrics": {
                "delay_risk": risk.get("delay_risk"),
                "stagnation_risk": risk.get("stagnation_risk"),
                "velocity_risk": risk.get("velocity_risk"),
            },
        }

        # Ensure shipping risks are associated with concrete suppliers by
        # inferring affected suppliers from the route/metadata and OEM scope,
        # and merging with any supplier labels that may already be present.
        existing_suppliers = _normalize_supplier_labels(risk.get("affectedSupplier"))
        inferred_suppliers = _infer_suppliers_for_route(scope, meta)

        all_suppliers: list[str] = []
        seen_labels: set[str] = set()
        for name in existing_suppliers + inferred_suppliers:
            label = name.strip()
            if not label:
                continue
            key = label.lower()
            if key in seen_labels:
                continue
            seen_labels.add(key)
            all_suppliers.append(label)

        db_risk = {
            "title": risk["title"],
            "description": risk["description"],
            "severity": risk.get("severity", "medium"),
            "affectedRegion": risk.get("affectedRegion"),
            "affectedSupplier": all_suppliers or None,
            "estimatedImpact": risk.get("estimatedImpact"),
            "estimatedCost": risk.get("estimatedCost"),
            "sourceType": "shipping",
            "sourceData": source_data,
        }
        risks_for_db.append(db_risk)

    return {"risks": risks_for_db}
