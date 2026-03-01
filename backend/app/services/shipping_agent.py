"""LLM-powered shipment risk analysis service (home-screen flow).

Uses the same system prompt and tracking pre-processing as the LangGraph
dashboard flow (``app.agents.shipment``) via the shared module
``app.services.shipping_shared``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.supplier import Supplier
from app.services.agent_types import OemScope
from app.services.shipping_shared import (
    SHIPMENT_FALLBACK_RESULT,
    SHIPMENT_RISK_SYSTEM_PROMPT,
    build_narrative_context,
    extract_tracking_data_from_records,
    parse_tracking_data_to_records,
)

logger = logging.getLogger(__name__)

SHIPMENT_TRACKING_COLLECTION = "shipment-tracking"


def _build_client() -> OpenAI:
    api_key = settings.openai_api_key
    base_url = settings.openai_base_url
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set to use the shipment agent.")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _get_supplier(db: Session, supplier_id: str) -> dict[str, Any] | None:
    """Fetch supplier details from the suppliers table by UUID."""
    print(f"\n[ShipmentAgent] DB query — suppliers WHERE id = '{supplier_id}'")
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        print(f"[ShipmentAgent] DB result — supplier NOT FOUND for id='{supplier_id}'")
        return None
    result = {
        "id": str(supplier.id),
        "name": supplier.name,
        "location": supplier.location,
        "city": supplier.city,
        "country": supplier.country,
        "region": supplier.region,
        "commodities": supplier.commodities,
    }
    print(f"[ShipmentAgent] DB result — supplier found: {json.dumps(result, indent=2)}")
    return result


def _get_tracking_for_supplier(supplier_id: str | None) -> list[dict[str, Any]]:
    """
    Fetch shipment tracking records from the mock server for a given supplier.

    GET {mock_server_base_url}/mock/shipment-tracking?q=supplier_id:{supplier_id}
    Returns list of record data dicts. Uses supplier_id to avoid issues with spaces in names.
    """
    base_url = settings.mock_server_base_url
    if not base_url or not (supplier_id or "").strip():
        logger.debug(
            "mock_server_base_url not configured or supplier_id empty — skipping tracking fetch"
        )
        return []

    supplier_id_str = (supplier_id or "").strip()
    url = (
        f"{base_url.rstrip('/')}/mock/{SHIPMENT_TRACKING_COLLECTION}"
        f"?q=supplier_id:{supplier_id_str}"
    )
    logger.info("Mock server request — GET %s", url)
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items") or []
        records = [item.get("data") or item for item in items]
        logger.info(
            "Mock server response — %s tracking record(s) for supplier_id=%s",
            len(records),
            supplier_id_str,
        )
        return records
    except Exception as exc:
        logger.warning("Mock server ERROR for supplier_id=%s: %s", supplier_id_str, exc)
        return []


def analyze_shipments_for_supplier(
    db: Session,
    scope: OemScope,
) -> dict[str, Any]:
    """Gather supplier/tracking data via DB and mock server; pass to LLM; return JSON."""

    print("\n" + "=" * 60)
    print("[ShipmentAgent] ▶ analyze_shipments_for_supplier called")
    print(f"[ShipmentAgent] Scope received from frontend:\n{json.dumps(dict(scope), indent=2)}")
    print("=" * 60)

    client = _build_client()

    supplier_id = scope.get("supplierId")
    supplier_name = scope.get("supplierName") or ""

    supplier_data: dict[str, Any] = {"name": supplier_name}
    if supplier_id:
        supplier_id_str = str(supplier_id).strip()
        fetched = _get_supplier(db, supplier_id_str)
        if fetched:
            supplier_data = fetched
            supplier_name = supplier_name or fetched.get("name") or ""
    else:
        logger.debug("No supplierId in scope — cannot fetch tracking by supplier_id")

    # Fetch raw records from mock server
    raw_records = _get_tracking_for_supplier(str(supplier_id).strip() if supplier_id else None)

    print(f"[ShipmentAgent] fetch_tracking — got {len(raw_records)} raw record(s)")
    print(f"[ShipmentAgent] Raw tracking records:\n{json.dumps(raw_records, indent=2)}")

    # Pre-process into structured records (same logic as dashboard flow)
    tracking_data = extract_tracking_data_from_records(raw_records)
    tracking_records = parse_tracking_data_to_records(tracking_data)

    print(f"[ShipmentAgent] Parsed {len(tracking_records)} structured tracking record(s)")
    print(f"[ShipmentAgent] Structured tracking_records:\n{json.dumps(tracking_records, indent=2, default=str)}")

    oem_context = {
        "id": scope.get("oemId"),
        "name": scope.get("oemName"),
        "locations": scope.get("locations"),
        "commodities": scope.get("commodities"),
    }

    # Build a human-readable narrative so the LLM reasons about route
    # progress, timing, and risk signals rather than raw JSON blobs.
    narrative = build_narrative_context(oem_context, supplier_data, tracking_records)

    print(f"\n[ShipmentAgent] LLM narrative context being sent:")
    print(narrative)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SHIPMENT_RISK_SYSTEM_PROMPT},
        {"role": "user", "content": narrative},
    ]

    print(f"\n[ShipmentAgent] Calling LLM — model={settings.openai_model}")

    response = client.chat.completions.create(
        model= "gpt-4o",
        response_format={"type": "json_object"},
        messages=messages,
    )

    llm_content = response.choices[0].message.content or "{}"

    try:
        data = json.loads(llm_content)
    except json.JSONDecodeError:
        print("[ShipmentAgent] LLM response was not valid JSON — using fallback")
        data = dict(SHIPMENT_FALLBACK_RESULT)
        data["risk_factors"] = ["Model returned non-JSON response"]
        data["recommended_actions"] = [llm_content]
        data["shipment_metadata"] = {"context": narrative}

    data.setdefault(
        "shipment_metadata",
        {"supplier": supplier_data, "tracking_count": len(tracking_records)},
    )

    print("\n[ShipmentAgent] ✓ Done — returning result to caller")
    print("=" * 60 + "\n")
    return data
