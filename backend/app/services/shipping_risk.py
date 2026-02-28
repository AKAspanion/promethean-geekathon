"""Shipping risk: delegates to LLM agent."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.agent_types import OemScope
from app.services.shipping_agent import analyze_shipments_for_supplier

logger = logging.getLogger(__name__)


def _normalize_agent_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Map agent response to the canonical risk dict shape."""
    return {
        "shipping_risk_score": float(raw.get("shipping_risk_score", 0.5)),
        "risk_level": str(raw.get("risk_level", "Medium")),
        "delay_risk": raw.get("delay_risk"),
        "stagnation_risk": raw.get("stagnation_risk"),
        "velocity_risk": raw.get("velocity_risk"),
        "risk_factors": list(raw.get("risk_factors", [])),
        "recommended_actions": list(raw.get("recommended_actions", [])),
        "shipment_metadata": raw.get("shipment_metadata"),
    }


def calculate_shipping_risk(scope: OemScope, db: Session) -> dict[str, Any]:
    """Run LLM agent and return normalized risk dict."""
    try:
        agent_result = analyze_shipments_for_supplier(db, scope)
        return _normalize_agent_result(agent_result)
    except Exception as exc:
        logger.exception("Shipping risk agent failed for supplier %s: %s", scope.get("supplierId"), exc)
        return {
            "shipping_risk_score": 0.5,
            "risk_level": "Medium",
            "delay_risk": {"score": 50, "label": "medium"},
            "stagnation_risk": {"score": 50, "label": "medium"},
            "velocity_risk": {"score": 0, "label": "low"},
            "risk_factors": ["Agent unavailable; risk could not be assessed"],
            "recommended_actions": ["Manually review shipments for this supplier"],
            "shipment_metadata": None,
        }
