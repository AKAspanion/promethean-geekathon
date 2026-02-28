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
import time
import uuid as _uuid
from typing import Any, TypedDict

import httpx
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from app.config import settings
from app.services.agent_orchestrator import _extract_json
from app.services.agent_types import OemScope
from app.services.langchain_llm import get_chat_model
from app.services.llm_client import _persist_llm_log
from app.services.shipping_shared import (
    SHIPMENT_FALLBACK_RESULT,
    SHIPMENT_RISK_SYSTEM_PROMPT,
    build_narrative_context,
    extract_tracking_data_from_records,
    parse_tracking_data_to_records,
)
from app.services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket broadcast helper
# ---------------------------------------------------------------------------


async def _broadcast_progress(
    step: str,
    message: str,
    details: dict | None = None,
    oem_name: str | None = None,
    supplier_name: str | None = None,
) -> None:
    """Broadcast a shipping agent progress event over websocket."""
    payload: dict = {
        "type": "shipping_agent_progress",
        "step": step,
        "message": message,
    }
    if oem_name:
        payload["oemName"] = oem_name
    if supplier_name:
        payload["supplierName"] = supplier_name
    if details:
        payload["details"] = details
    await ws_manager.broadcast(payload)


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


# Alias so existing references inside this module continue to work
_FALLBACK_RESULT = SHIPMENT_FALLBACK_RESULT


# ---------------------------------------------------------------------------
# LLM chain
# ---------------------------------------------------------------------------

# System prompt is now sourced from shipping_shared — edit it there to affect both flows
_RISK_SYSTEM_PROMPT = SHIPMENT_RISK_SYSTEM_PROMPT

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
    oem_name = scope.get("oemName") or ""

    print("\n" + "=" * 60)
    print("[ShipmentAgent/Graph] ▶ fetch_tracking_node called")
    print(f"[ShipmentAgent/Graph] Scope received:\n{json.dumps(dict(scope), indent=2)}")
    print(f"[ShipmentAgent/Graph] supplier_id={supplier_id!r}  supplier_name={supplier_name!r}")
    print("=" * 60)

    await _broadcast_progress(
        "fetch_tracking", f"Fetching tracking data for {supplier_name or supplier_id}",
        oem_name=oem_name, supplier_name=supplier_name,
    )

    if not supplier_id:
        logger.warning("fetch_tracking — no supplierId in scope, skipping fetch")
        await _broadcast_progress(
            "fetch_tracking_done", "No supplier ID — skipped tracking fetch",
            details={"records": 0},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {
            "shipping_data": {
                "supplier_id": "",
                "supplier_name": supplier_name,
                "tracking_data": {},
            }
        }

    records = await _fetch_tracking_from_mock_server(supplier_id)

    print(f"[ShipmentAgent/Graph] fetch_tracking — got {len(records)} record(s) for supplier_id={supplier_id!r}")
    print(f"[ShipmentAgent/Graph] Raw tracking records:\n{json.dumps(records, indent=2)}")

    # Extract tracking_data from raw records (shared utility — same as home-screen flow)
    tracking_data = extract_tracking_data_from_records(records)

    print(f"[ShipmentAgent/Graph] Extracted tracking_data keys: {list(tracking_data.keys()) if tracking_data else '(empty)'}")

    logger.info(
        "fetch_tracking — supplier=%s (%s), got %d record(s)",
        supplier_name,
        supplier_id,
        len(records),
    )

    await _broadcast_progress(
        "fetch_tracking_done",
        f"Fetched {len(records)} tracking record(s) for {supplier_name or supplier_id}",
        details={"records": len(records)},
        oem_name=oem_name, supplier_name=supplier_name,
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


async def _build_metadata_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Parse tracking data into structured tracking records.

    Expects ``tracking_data`` with ``route_plan`` (list of checkpoint dicts)
    and ``shipment_meta`` (origin, destination, etd, pickup_date, etc.).
    Computes per-shipment metrics (delay, stagnation, velocity) that
    ``_heuristic_from_tracking`` can consume.
    """
    print("\n[ShipmentAgent/Graph] ▶ build_metadata_node called")
    shipping_data = state.get("shipping_data") or {}

    # --- Supplier info ---
    # OemScope does not have dedicated supplierCity/supplierCountry keys.
    # build_oem_supplier_scope() merges the supplier's city/country/commodities
    # into the top-level cities/countries/commodities lists, so we read from there.
    scope = state.get("scope") or {}
    scope_cities: list = scope.get("cities") or []
    scope_countries: list = scope.get("countries") or []
    scope_commodities: list = scope.get("commodities") or []
    supplier_data: dict[str, Any] = {
        "id": shipping_data.get("supplier_id") or "",
        "name": shipping_data.get("supplier_name") or "",
        "location": (scope.get("locations") or [""])[0],
        "city": scope_cities[0] if scope_cities else "",
        "country": scope_countries[0] if scope_countries else "",
        "commodities": scope_commodities,
    }

    # --- Tracking data (parsed via shared utility — same as home-screen flow) ---
    tracking_data = shipping_data.get("tracking_data") or {}
    tracking_records = parse_tracking_data_to_records(tracking_data)

    print(f"[ShipmentAgent/Graph] build_metadata — parsed {len(tracking_records)} shipment(s)")
    print(f"[ShipmentAgent/Graph] Structured tracking_records:\n{json.dumps(tracking_records, indent=2, default=str)}")

    logger.info(
        "build_metadata — %d shipment(s) for supplier %s",
        len(tracking_records),
        supplier_data.get("name") or supplier_data.get("id"),
    )

    scope = state.get("scope") or {}
    await _broadcast_progress(
        "build_metadata_done",
        f"Parsed {len(tracking_records)} shipment(s) for {supplier_data.get('name') or 'supplier'}",
        details={"shipments": len(tracking_records)},
        oem_name=scope.get("oemName") or "",
        supplier_name=scope.get("supplierName") or "",
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
    print("\n[ShipmentAgent/Graph] ▶ analyze_risk_node called")
    scope = state.get("scope") or {}
    supplier_data = state.get("supplier_data") or {}
    tracking_records = state.get("tracking_records") or []
    oem_name = scope.get("oemName") or ""
    supplier_name = scope.get("supplierName") or ""

    print(f"[ShipmentAgent/Graph]   Supplier : {json.dumps(supplier_data)}")
    print(f"[ShipmentAgent/Graph]   Tracking records: {len(tracking_records)}")

    chain = _get_risk_chain()
    if not chain:
        logger.info("No LLM configured — using heuristic fallback")
        await _broadcast_progress(
            "heuristic_fallback", "No LLM configured — using heuristic analysis",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {
            "shipping_risk_result": _heuristic_from_tracking(
                tracking_records, supplier_data
            )
        }

    # Derive provider/model for logging
    llm = get_chat_model()
    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]

    oem_context = {
        "id": scope.get("oemId"),
        "name": scope.get("oemName"),
        "locations": scope.get("locations"),
        "commodities": scope.get("commodities"),
    }

    # Build a human-readable narrative instead of raw JSON so the LLM
    # can reason naturally about route progress, timing, and risk signals.
    narrative = build_narrative_context(oem_context, supplier_data, tracking_records)
    context_json = narrative  # sent as the user message
    prompt_text = _RISK_SYSTEM_PROMPT + "\n\n" + narrative

    print(f"\n[ShipmentAgent/Graph] LLM narrative context being sent:")
    print(narrative)
    print(f"\n[ShipmentAgent/Graph] Calling LLM — provider={getattr(get_chat_model(), 'model_provider', 'unknown')} model={getattr(get_chat_model(), 'model_name', None) or getattr(get_chat_model(), 'model', 'unknown')}")

    start = time.perf_counter()
    try:
        logger.info(
            "[ShipmentAgent] LLM request id=%s provider=%s model=%s prompt_len=%d",
            call_id, provider, model_name, len(prompt_text),
        )
        await _broadcast_progress(
            "llm_start", f"Running shipment risk analysis",
            details={"call_id": call_id, "provider": provider, "model": str(model_name)},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        msg = await chain.ainvoke({"context_json": context_json})
        elapsed = int((time.perf_counter() - start) * 1000)

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

        logger.info(
            "[ShipmentAgent] LLM response id=%s provider=%s elapsed_ms=%d response_len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, raw_text, "success", elapsed, None,
        )

        print(f"\n[ShipmentAgent/Graph] LLM raw response:\n{raw_text}")

        parsed = _extract_json(raw_text) or {}
        score = parsed.get("shipping_risk_score")
        print(f"\n[ShipmentAgent/Graph] LLM parsed result:\n{json.dumps(parsed, indent=2)}")
        logger.info(
            "LLM risk analysis completed — score=%s elapsed_ms=%d",
            score, elapsed,
        )
        await _broadcast_progress(
            "llm_done", f"Shipment risk analysis complete (score: {score})",
            details={"score": score, "elapsed_ms": elapsed},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"shipping_risk_result": parsed}
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("Shipping risk LLM error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, None, "error", elapsed, str(exc),
        )
        await _broadcast_progress(
            "llm_error", f"LLM error: {exc}",
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {
            "shipping_risk_result": _heuristic_from_tracking(
                tracking_records, supplier_data
            )
        }


# ---------------------------------------------------------------------------
# Node: normalize_result
# ---------------------------------------------------------------------------


async def _normalize_result_node(state: ShipmentGraphState) -> dict[str, Any]:
    """Ensure all expected keys exist with safe defaults."""
    print("\n[ShipmentAgent/Graph] ▶ normalize_result_node called")
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

    print(f"[ShipmentAgent/Graph] Normalized result:\n{json.dumps(result, indent=2)}")
    print("\n[ShipmentAgent/Graph] ✓ Done — returning result to caller")
    print("=" * 60 + "\n")

    scope = state.get("scope") or {}
    await _broadcast_progress(
        "completed",
        f"Shipment risk analysis complete — level: {result.get('risk_level', 'Medium')}",
        details={
            "risk_level": result.get("risk_level"),
            "score": result.get("shipping_risk_score"),
            "risks": 1,  # single aggregate risk entry
        },
        oem_name=scope.get("oemName") or "",
        supplier_name=scope.get("supplierName") or "",
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

    Returns the same ``{"risks": [...]}`` shape that news / weather agents
    produce so callers can consume shipment results uniformly.

    Parameters
    ----------
    scope:
        OEM / supplier context.  Must include ``supplierId`` (and ideally
        ``supplierName``) so that the ``fetch_tracking`` node can retrieve
        shipment records from the mock server.

    Returns
    -------
    dict
        ``{"risks": [<db-ready risk dicts>]}``
    """
    initial_state: ShipmentGraphState = {
        "scope": scope,
    }
    final_state = await SHIPMENT_RISK_GRAPH.ainvoke(initial_state)
    risk_result = final_state.get("shipping_risk_result") or dict(_FALLBACK_RESULT)
    return {
        "risks": shipping_risk_result_to_db_risks(risk_result, scope),
        "tracking_records": final_state.get("tracking_records") or [],
        "supplier_data": final_state.get("supplier_data") or {},
        "shipping_risk_result": risk_result,
    }


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

