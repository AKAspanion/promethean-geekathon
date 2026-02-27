"""LLM-powered shipment risk agent (OpenAI-compatible)."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.shipping_supplier import ShippingSupplier
from app.models.shipment import Shipment
from app.services.mock_tracking import get_tracking


def _build_client() -> OpenAI:
    api_key = settings.openai_api_key
    base_url = settings.openai_base_url
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set to use the shipment agent.")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


SYSTEM_PROMPT = """You are a Shipment Risk Intelligence Agent.

You will be given JSON context: supplier details, shipments, tracking events.

Your goals:
1. Construct shipment metadata (shipments + tracking timeline).
2. Calculate Delay Risk, Stagnation Risk, Velocity Risk.
3. Produce a JSON with: shipping_risk_score (0-1), risk_level
   (Low/Medium/High/Critical), delay_probability, delay_risk_score,
   stagnation_risk_score, velocity_risk_score, risk_factors,
   recommended_actions, shipment_metadata.

Respond strictly as a single JSON object; no prose outside JSON.
"""


def _tool_get_supplier_details(db: Session, supplier_id: int) -> dict[str, Any]:
    supplier = (
        db.query(ShippingSupplier).filter(ShippingSupplier.id == supplier_id).first()
    )
    if not supplier:
        return {"error": f"Supplier {supplier_id} not found"}
    return {
        "id": supplier.id,
        "name": supplier.name,
        "material_name": supplier.material_name,
        "origin_city": supplier.location_city,
        "destination_city": supplier.destination_city,
        "shipping_mode": supplier.shipping_mode,
        "distance_km": supplier.distance_km,
        "avg_transit_days": supplier.avg_transit_days,
    }


def _tool_get_shipments_for_supplier(
    db: Session, supplier_id: int
) -> list[dict[str, Any]]:
    shipments = db.query(Shipment).filter(Shipment.supplier_id == supplier_id).all()
    return [
        {
            "id": sh.id,
            "awb_code": sh.awb_code,
            "courier_name": sh.courier_name,
            "origin_city": sh.origin_city,
            "destination_city": sh.destination_city,
            "pickup_date": (sh.pickup_date.isoformat() if sh.pickup_date else None),
            "expected_delivery_date": (
                sh.expected_delivery_date.isoformat()
                if sh.expected_delivery_date
                else None
            ),
            "delivered_date": (
                sh.delivered_date.isoformat() if sh.delivered_date else None
            ),
            "current_status": sh.current_status,
            "weight": sh.weight,
            "packages": sh.packages,
        }
        for sh in shipments
    ]


def _tool_get_shipment_tracking(awb_code: str) -> dict[str, Any]:
    tracking = get_tracking(awb_code)
    if tracking is None:
        return {"error": f"No tracking found for AWB {awb_code}"}
    return tracking


def analyze_shipments_for_supplier(
    db: Session, supplier: ShippingSupplier
) -> dict[str, Any]:
    """Gather supplier/shipment/tracking data; pass to LLM; return JSON."""
    client = _build_client()

    supplier_data = _tool_get_supplier_details(db, supplier.id)
    shipments = _tool_get_shipments_for_supplier(db, supplier.id)

    tracking_by_awb: dict[str, Any] = {}
    for sh in shipments:
        awb = sh.get("awb_code")
        if not awb:
            continue
        tracking_by_awb[awb] = _tool_get_shipment_tracking(awb)

    context = {
        "supplier": supplier_data,
        "shipments": shipments,
        "tracking_by_awb": tracking_by_awb,
    }

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"context": context})},
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=messages,
    )

    choice = response.choices[0]
    message = choice.message
    content = message.content or "{}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "shipping_risk_score": 0.5,
            "risk_level": "Medium",
            "delay_probability": 0.5,
            "delay_risk_score": None,
            "stagnation_risk_score": None,
            "velocity_risk_score": None,
            "risk_factors": ["Model returned non-JSON response"],
            "recommended_actions": [content],
            "shipment_metadata": {"context": context},
        }

    data.setdefault("shipment_metadata", context)
    return data
