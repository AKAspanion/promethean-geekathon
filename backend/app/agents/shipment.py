"""LangGraph-based shipment risk analysis agent.

Single entry point:

* ``run_shipment_risk_graph(scope)``
    Fetches tracking data from the mock server, parses it, runs LLM
    analysis (with heuristic fallback), and returns a
    ``ShippingRiskResult`` dict.

Graph: fetch_tracking -> build_metadata -> analyze_risk -> normalize_result -> END
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, TypedDict

import httpx
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from app.config import settings
from app.services.agent_orchestrator import _extract_json
from app.services.agent_types import OemScope
from app.services.langchain_llm import get_chat_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _band(score: int) -> str:
    """Map a 0-100 score to a risk band label."""
    if score <= 25:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


def _risk_level_from_score(score: float) -> str:
    """Map a 0.0-1.0 score to a capitalised risk level."""
    if score <= 0.25:
        return "Low"
    if score <= 0.50:
        return "Medium"
    if score <= 0.75:
        return "High"
    return "Critical"


_FALLBACK_RESULT: dict[str, Any] = {
    "shipping_risk_score": 0.5,
    "risk_level": "Medium",
    "delay_risk": {"score": 50, "label": "medium"},
    "stagnation_risk": {"score": 50, "label": "medium"},
    "velocity_risk": {"score": 0, "label": "low"},
    "risk_factors": ["Agent unavailable; risk could not be assessed"],
    "recommended_actions": ["Manually review shipments for this supplier"],
    "shipment_metadata": None,
}


# ---------------------------------------------------------------------------
# LLM chain
# ---------------------------------------------------------------------------

_RISK_SYSTEM_PROMPT = (
    "You are a Shipment Risk Intelligence Agent for a manufacturing "
    "supply chain.\n\n"
    "You will be given JSON context containing:\n"
    "- oem: OEM details (id, name, locations, commodities)\n"
    "- supplier: Supplier details (name, city, country, region, commodities)\n"
    "- tracking: List of shipment tracking records for this supplier\n\n"
    "Your goals:\n"
    "1. Analyze the tracking timeline for delays, stagnation, and velocity "
    "anomalies.\n"
    "2. Calculate risk scores (0-100) for delay_risk, stagnation_risk, and "
    "velocity_risk.\n"
    "3. Identify specific risk factors from the data.\n"
    "4. Produce concrete, actionable recommendations to mitigate the risks."
    "\n\n"
    "Return a single JSON object with this exact shape:\n"
    "{{\n"
    '  "shipping_risk_score": <float 0.0-1.0>,\n'
    '  "risk_level": <"Low" | "Medium" | "High" | "Critical">,\n'
    '  "delay_risk": {{ "score": <0-100>, "label": '
    '<"low"|"medium"|"high"|"critical"> }},\n'
    '  "stagnation_risk": {{ "score": <0-100>, "label": '
    '<"low"|"medium"|"high"|"critical"> }},\n'
    '  "velocity_risk": {{ "score": <0-100>, "label": '
    '<"low"|"medium"|"high"|"critical"> }},\n'
    '  "risk_factors": [<string>, ...],\n'
    '  "recommended_actions": [<string>, ...],\n'
    '  "shipment_metadata": {{ <summary of key fields> }}\n'
    "}}\n\n"
    "Respond strictly as a single JSON object; no prose outside JSON."
)

_risk_prompt: ChatPromptTemplate | None = None


def _get_risk_chain() -> Any | None:
    """Build a LangChain chain for shipment risk analysis.

    Returns None when no LLM is configured (callers use heuristic fallback).
    """
    global _risk_prompt

    llm = get_chat_model()
    if llm is None:
        return None

    if _risk_prompt is None:
        _risk_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _RISK_SYSTEM_PROMPT),
                ("user", "{context_json}"),
            ]
        )
    return _risk_prompt | llm


# ---------------------------------------------------------------------------
# Tracking data fetch
# ---------------------------------------------------------------------------

SHIPMENT_TRACKING_COLLECTION = "shipment-tracking"


async def _fetch_tracking_from_mock_server(
    supplier_id: str,
) -> list[dict[str, Any]]:
    """Fetch shipment tracking records from the mock server for a supplier.

    GET {mock_server_base_url}/mock/shipment-tracking?q=supplier_id:{supplier_id}
    """
    base_url = settings.mock_server_base_url
    if not base_url or not supplier_id.strip():
        logger.debug(
            "mock_server_base_url not configured or supplier_id empty — "
            "skipping tracking fetch"
        )
        return []

    url = (
        f"{base_url.rstrip('/')}/mock/{SHIPMENT_TRACKING_COLLECTION}"
        f"?q=supplier_id:{supplier_id.strip()}"
    )
    logger.info("fetch_tracking — GET %s", url)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items") or []
        records = [item.get("data") or item for item in items]
        logger.info(
            "fetch_tracking — %d record(s) for supplier_id=%s",
            len(records),
            supplier_id,
        )
        return records
    except Exception as exc:
        logger.warning("fetch_tracking — error for supplier_id=%s: %s", supplier_id, exc)
        return []


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------


class ShipmentGraphState(TypedDict, total=False):
    """State for the shipment risk graph."""

    scope: OemScope  # OEM context for LLM
    shipping_data: dict[str, Any]  # Built by fetch_tracking (or passed in)
    supplier_data: dict[str, Any]  # Set by build_metadata
    tracking_records: list[dict[str, Any]]  # Set by build_metadata
    shipping_risk_result: dict[str, Any]  # Set by analyze_risk / normalize


# ---------------------------------------------------------------------------
# Node: fetch_tracking
# ---------------------------------------------------------------------------


async def _fetch_tracking_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Fetch tracking data from the mock server using supplier info in scope.

    Populates ``shipping_data`` with supplier id/name and raw tracking data
    so that downstream ``build_metadata`` can parse it.
    """
    scope = state.get("scope") or {}
    supplier_id = str(scope.get("supplierId") or "").strip()
    supplier_name = scope.get("supplierName") or ""

    if not supplier_id:
        logger.warning("fetch_tracking — no supplierId in scope, skipping fetch")
        return {
            "shipping_data": {
                "supplier_id": "",
                "supplier_name": supplier_name,
                "tracking_data": {},
            }
        }

    records = await _fetch_tracking_from_mock_server(supplier_id)

    # The mock server returns a list of tracking record dicts.  Use the first
    # record's tracking_data (Shiprocket format) if available.
    tracking_data: dict[str, Any] = {}
    if records:
        first = records[0]
        if isinstance(first, dict):
            tracking_data = first.get("tracking_data") or first

    logger.info(
        "fetch_tracking — supplier=%s (%s), got %d record(s)",
        supplier_name,
        supplier_id,
        len(records),
    )

    return {
        "shipping_data": {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "tracking_data": tracking_data,
        }
    }


# ---------------------------------------------------------------------------
# Node: build_metadata
# ---------------------------------------------------------------------------


def _parse_datetime(raw: str | None) -> datetime | None:
    """Best-effort parse of a datetime string."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


def _max_activity_gap_days(
    activities: list[dict[str, Any]],
) -> int:
    """Compute the largest gap (in days) between consecutive activities."""
    dates: list[datetime] = []
    for act in activities:
        dt = _parse_datetime(act.get("date"))
        if dt:
            dates.append(dt)
    if len(dates) < 2:
        return 0
    dates.sort()
    max_gap = 0
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap > max_gap:
            max_gap = gap
    return max_gap


def _build_metadata_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Parse Shiprocket-style shipping_data into structured tracking records.

    Extracts supplier info and computes per-shipment metrics (delay,
    stagnation, velocity) that ``_heuristic_from_tracking`` can consume.
    """
    shipping_data = state.get("shipping_data") or {}

    # --- Supplier info ---
    supplier_data: dict[str, Any] = {
        "id": shipping_data.get("supplier_id") or "",
        "name": shipping_data.get("supplier_name") or "",
    }

    # --- Tracking data ---
    tracking_data = shipping_data.get("tracking_data") or {}
    shipment_tracks = tracking_data.get("shipment_track") or []
    activities = tracking_data.get("shipment_track_activities") or []
    etd_raw = tracking_data.get("etd")
    etd_dt = _parse_datetime(etd_raw)

    tracking_records: list[dict[str, Any]] = []

    for track in shipment_tracks:
        if not isinstance(track, dict):
            continue

        origin = track.get("origin") or ""
        destination = track.get("destination") or ""
        route = f"{origin} → {destination}" if origin and destination else "unknown"
        current_status = track.get("current_status") or "unknown"
        pickup_date_dt = _parse_datetime(track.get("pickup_date"))

        # Sort activities chronologically
        sorted_activities = sorted(
            (a for a in activities if isinstance(a, dict) and a.get("date")),
            key=lambda a: a["date"],
        )

        # Last activity date
        last_activity_dt = (
            _parse_datetime(sorted_activities[-1]["date"])
            if sorted_activities
            else None
        )

        # Compute planned transit days (pickup → ETD)
        planned_transit_days = 0
        if pickup_date_dt and etd_dt:
            planned_transit_days = max(1, (etd_dt - pickup_date_dt).days)

        # Compute actual transit days (pickup → last activity)
        actual_transit_days = planned_transit_days
        if pickup_date_dt and last_activity_dt:
            actual_transit_days = max(1, (last_activity_dt - pickup_date_dt).days)

        # Delay: how many days past ETD
        delay_days = 0
        if etd_dt and last_activity_dt and last_activity_dt > etd_dt:
            delay_days = (last_activity_dt - etd_dt).days

        # Stagnation: max gap between consecutive activities
        days_without_movement = _max_activity_gap_days(sorted_activities)

        record: dict[str, Any] = {
            "route": route,
            "origin": origin,
            "destination": destination,
            "status": current_status,
            "delayDays": delay_days,
            "daysWithoutMovement": days_without_movement,
            "plannedTransitDays": planned_transit_days,
            "actualTransitDays": actual_transit_days,
            "activities": sorted_activities,
        }
        tracking_records.append(record)

    logger.info(
        "build_metadata — %d shipment(s) for supplier %s",
        len(tracking_records),
        supplier_data.get("name") or supplier_data.get("id"),
    )
    return {
        "supplier_data": supplier_data,
        "tracking_records": tracking_records,
    }


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------


def _heuristic_from_tracking(
    tracking_records: list[dict[str, Any]],
    supplier_data: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic heuristic fallback when no LLM is configured."""
    if not tracking_records:
        return dict(_FALLBACK_RESULT)

    total_delay = 0
    total_stagnation = 0
    total_velocity_dev = 0.0
    count = 0
    risk_factors: list[str] = []

    for record in tracking_records:
        if not isinstance(record, dict):
            continue
        delay = int(record.get("delayDays") or 0)
        stagnation = int(record.get("daysWithoutMovement") or 0)
        planned = int(record.get("plannedTransitDays") or 0) or 1
        actual = int(record.get("actualTransitDays") or 0) or planned

        total_delay += delay
        total_stagnation += stagnation
        total_velocity_dev += abs(actual / planned - 1.0)
        count += 1

        route = record.get("route") or "unknown"
        if delay > 0:
            risk_factors.append(f"Route {route}: {delay} day(s) delayed")
        if stagnation > 0:
            risk_factors.append(
                f"Route {route}: {stagnation} day(s) without movement"
            )

    if count == 0:
        return dict(_FALLBACK_RESULT)

    avg_delay = total_delay / count
    avg_stagnation = total_stagnation / count
    avg_velocity_dev = total_velocity_dev / count

    delay_score = min(100, int(avg_delay * 10))
    stagnation_score = min(100, int(avg_stagnation * 15))
    velocity_score = min(100, int(avg_velocity_dev * 40))
    max_score = max(delay_score, stagnation_score, velocity_score)

    return {
        "shipping_risk_score": round(max_score / 100.0, 2),
        "risk_level": _risk_level_from_score(max_score / 100.0),
        "delay_risk": {"score": delay_score, "label": _band(delay_score)},
        "stagnation_risk": {
            "score": stagnation_score,
            "label": _band(stagnation_score),
        },
        "velocity_risk": {
            "score": velocity_score,
            "label": _band(velocity_score),
        },
        "risk_factors": risk_factors or ["No significant risks detected"],
        "recommended_actions": (
            ["Review delayed shipments", "Monitor stagnating routes"]
            if max_score > 25
            else ["Continue standard monitoring"]
        ),
        "shipment_metadata": {
            "supplier": supplier_data,
            "tracking_count": len(tracking_records),
        },
    }


# ---------------------------------------------------------------------------
# Node: analyze_risk
# ---------------------------------------------------------------------------


async def _analyze_risk_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Build LLM context from metadata and run risk analysis."""
    scope = state.get("scope") or {}
    supplier_data = state.get("supplier_data") or {}
    tracking_records = state.get("tracking_records") or []

    chain = _get_risk_chain()
    if not chain:
        logger.info("No LLM configured — using heuristic fallback")
        return {
            "shipping_risk_result": _heuristic_from_tracking(
                tracking_records, supplier_data
            )
        }

    context = {
        "oem": {
            "id": scope.get("oemId"),
            "name": scope.get("oemName"),
            "locations": scope.get("locations"),
            "commodities": scope.get("commodities"),
        },
        "supplier": supplier_data,
        "tracking": tracking_records,
    }

    try:
        context_json = json.dumps({"context": context})
        msg = await chain.ainvoke({"context_json": context_json})

        # Extract text from LLM response (handles Anthropic content blocks)
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
        logger.info(
            "LLM risk analysis completed — score=%s",
            parsed.get("shipping_risk_score"),
        )
        return {"shipping_risk_result": parsed}
    except Exception as exc:
        logger.exception("Shipping risk LLM error: %s", exc)
        return {
            "shipping_risk_result": _heuristic_from_tracking(
                tracking_records, supplier_data
            )
        }


# ---------------------------------------------------------------------------
# Node: normalize_result
# ---------------------------------------------------------------------------


def _normalize_result_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Ensure all expected keys exist with safe defaults."""
    result = dict(state.get("shipping_risk_result") or {})

    result.setdefault("shipping_risk_score", 0.5)
    result.setdefault("risk_level", "Medium")
    result.setdefault("delay_risk", {"score": 50, "label": "medium"})
    result.setdefault("stagnation_risk", {"score": 50, "label": "medium"})
    result.setdefault("velocity_risk", {"score": 0, "label": "low"})
    result.setdefault("risk_factors", [])
    result.setdefault("recommended_actions", [])
    result.setdefault(
        "shipment_metadata",
        {
            "supplier": state.get("supplier_data") or {},
            "tracking_count": len(state.get("tracking_records") or []),
        },
    )

    return {"shipping_risk_result": result}


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

_builder = StateGraph(ShipmentGraphState)
_builder.add_node("fetch_tracking", _fetch_tracking_node)
_builder.add_node("build_metadata", _build_metadata_node)
_builder.add_node("analyze_risk", _analyze_risk_node)
_builder.add_node("normalize_result", _normalize_result_node)
_builder.set_entry_point("fetch_tracking")
_builder.add_edge("fetch_tracking", "build_metadata")
_builder.add_edge("build_metadata", "analyze_risk")
_builder.add_edge("analyze_risk", "normalize_result")
_builder.add_edge("normalize_result", END)

SHIPMENT_RISK_GRAPH = _builder.compile()


async def run_shipment_risk_graph(
    scope: OemScope,
) -> dict[str, Any]:
    """Run shipment risk analysis for a supplier.

    The graph fetches tracking data from the mock server automatically
    using ``supplierId`` from *scope*, then analyses it for risk.

    Parameters
    ----------
    scope:
        OEM / supplier context.  Must include ``supplierId`` (and ideally
        ``supplierName``) so that the ``fetch_tracking`` node can retrieve
        shipment records from the mock server.

    Returns
    -------
    dict
        ShippingRiskResult::

            {
                "shipping_risk_score": float,       # 0.0-1.0
                "risk_level": str,                  # Low|Medium|High|Critical
                "delay_risk": {"score": int, "label": str},
                "stagnation_risk": {"score": int, "label": str},
                "velocity_risk": {"score": int, "label": str},
                "risk_factors": [str],
                "recommended_actions": [str],
                "shipment_metadata": dict | None,
            }
    """
    initial_state: ShipmentGraphState = {
        "scope": scope,
    }
    final_state = await SHIPMENT_RISK_GRAPH.ainvoke(initial_state)
    return final_state.get("shipping_risk_result") or dict(_FALLBACK_RESULT)


# ---------------------------------------------------------------------------
# Bridge: convert ShippingRiskResult → create_risk_from_dict dicts
# ---------------------------------------------------------------------------


def shipping_risk_result_to_db_risks(
    result: dict[str, Any],
    scope: OemScope,
) -> list[dict[str, Any]]:
    """Convert a ``ShippingRiskResult`` dict into risk dicts for
    ``create_risk_from_dict``.

    Produces a single risk entry representing the aggregate shipping risk
    for this supplier.  The ``sourceData.riskMetrics`` structure is
    preserved for downstream ``_compute_risk_score`` compatibility.
    """
    risk_level = result.get("risk_level", "Medium")
    score = result.get("shipping_risk_score", 0.5)
    severity = risk_level.lower() if risk_level else "medium"

    factors = result.get("risk_factors") or []
    actions = result.get("recommended_actions") or []
    description_parts: list[str] = []
    if factors:
        description_parts.append("Risk factors: " + "; ".join(factors))
    if actions:
        description_parts.append(
            "Recommended actions: " + "; ".join(actions)
        )
    description = (
        ". ".join(description_parts)
        or f"Shipping risk level: {risk_level}"
    )

    supplier_name = scope.get("supplierName") or ""

    source_data: dict[str, Any] = {
        "riskMetrics": {
            "delay_risk": result.get("delay_risk"),
            "stagnation_risk": result.get("stagnation_risk"),
            "velocity_risk": result.get("velocity_risk"),
        },
        "shipmentMetadata": result.get("shipment_metadata"),
        "shipping_risk_score": score,
    }

    return [
        {
            "title": (
                f"Shipping risk for {supplier_name or 'supplier'}"
                f" (score: {score})"
            ),
            "description": description,
            "severity": severity,
            "affectedRegion": None,
            "affectedSupplier": [supplier_name] if supplier_name else None,
            "estimatedImpact": f"Shipping risk score {score} ({risk_level})",
            "estimatedCost": None,
            "sourceType": "shipping",
            "sourceData": source_data,
        }
    ]

