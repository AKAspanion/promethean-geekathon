"""LLM-powered shipment risk analysis service."""

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


SYSTEM_PROMPT = """You are a Shipment Risk Intelligence Agent for a manufacturing supply chain.

You will be given JSON context containing:
- oem: OEM details (id, name, locations, commodities)
- supplier: Supplier details (name, city, country, region, commodities)
- tracking: List of shipment tracking records for this supplier

Your goals:
1. Analyze the tracking timeline for delays, stagnation, and velocity anomalies.
2. Calculate risk scores (0-100) for delay_risk, stagnation_risk, and velocity_risk.
3. Identify specific risk factors from the data.
4. Produce concrete, actionable recommendations to mitigate the risks.

Return a single JSON object with this exact shape:
{
  "shipping_risk_score": <float 0.0-1.0>,
  "risk_level": <"Low" | "Medium" | "High" | "Critical">,
  "delay_risk": { "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> },
  "stagnation_risk": { "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> },
  "velocity_risk": { "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> },
  "risk_factors": [<string>, ...],
  "recommended_actions": [<string>, ...],
  "shipment_metadata": { <summary of key fields> }
}

Respond strictly as a single JSON object; no prose outside JSON."""


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

    tracking_records = _get_tracking_for_supplier(str(supplier_id).strip() if supplier_id else None)

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

    print(f"\n[ShipmentAgent] LLM context being sent:")
    print(f"  OEM   : id={context['oem']['id']}  name={context['oem']['name']}")
    print(f"  Supplier: {json.dumps(supplier_data)}")
    print(f"  Tracking records: {len(tracking_records)}")
    print(f"  Tracking records: {json.dumps(tracking_records, indent=2)}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"context": context})},
    ]

    print(f"\n[ShipmentAgent] Calling LLM — model={settings.openai_model or 'gpt-4o'}")

    response = client.chat.completions.create(
        model=settings.openai_model or "gpt-4o",
        response_format={"type": "json_object"},
        messages=messages,
    )

    content = response.choices[0].message.content or "{}"
    print(f"\n[ShipmentAgent] LLM raw response:\n{content}")

    try:
        data = json.loads(content)
        print(f"\n[ShipmentAgent] LLM parsed result:\n{json.dumps(data, indent=2)}")
    except json.JSONDecodeError:
        print("[ShipmentAgent] LLM response was not valid JSON — using fallback")
        data = {
            "shipping_risk_score": 0.5,
            "risk_level": "Medium",
            "delay_risk": {"score": 50, "label": "medium"},
            "stagnation_risk": {"score": 50, "label": "medium"},
            "velocity_risk": {"score": 0, "label": "low"},
            "risk_factors": ["Model returned non-JSON response"],
            "recommended_actions": [content],
            "shipment_metadata": {"context": context},
        }

    data.setdefault(
        "shipment_metadata",
        {"supplier": supplier_data, "tracking_count": len(tracking_records)},
    )

    print("\n[ShipmentAgent] ✓ Done — returning result to caller")
    print("=" * 60 + "\n")
    return data
