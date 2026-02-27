"""Shipping risk: LLM agent with heuristic fallback."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.shipping_supplier import ShippingSupplier
from app.services.shipping_agent import analyze_shipments_for_supplier


def calculate_mode_risk(shipping_mode: str) -> float:
    mode = (shipping_mode or "").lower()
    if mode == "sea":
        return 0.7
    if mode == "road":
        return 0.5
    if mode == "rail":
        return 0.4
    if mode == "air":
        return 0.2
    return 0.5


def calculate_distance_risk(distance_km: float | None) -> float:
    if distance_km is None:
        return 0.4
    if distance_km <= 300:
        return 0.2
    if distance_km <= 1000:
        return 0.4
    if distance_km <= 3000:
        return 0.6
    return 0.8


def calculate_transit_risk(avg_transit_days: float | None) -> float:
    if avg_transit_days is None:
        return 0.5
    if avg_transit_days <= 3:
        return 0.2
    if avg_transit_days <= 7:
        return 0.4
    if avg_transit_days <= 15:
        return 0.6
    return 0.8


_PORT_CONGESTION: dict[str, float] = {
    "chennai port": 0.7,
    "los angeles": 0.8,
    "long beach": 0.8,
    "singapore": 0.5,
    "shanghai": 0.7,
}


def calculate_port_congestion_risk(port_used: str | None) -> float:
    if not port_used:
        return 0.4
    return _PORT_CONGESTION.get(port_used.lower(), 0.5)


def calculate_historical_delay_risk(historical_delay_percentage: float | None) -> float:
    if historical_delay_percentage is None:
        return 0.4
    return max(0.0, min(historical_delay_percentage / 100.0, 1.0))


def calculate_redundancy_risk(
    alternate_route_available: bool, is_critical_supplier: bool
) -> float:
    if is_critical_supplier and not alternate_route_available:
        return 1.0
    if not is_critical_supplier and not alternate_route_available:
        return 0.7
    if is_critical_supplier and alternate_route_available:
        return 0.5
    return 0.2


def calculate_shipping_risk_heuristic(supplier: ShippingSupplier) -> dict[str, Any]:
    mode_risk = calculate_mode_risk(supplier.shipping_mode)
    distance_risk = calculate_distance_risk(supplier.distance_km)
    transit_risk = calculate_transit_risk(supplier.avg_transit_days)
    port_risk = calculate_port_congestion_risk(supplier.port_used)
    historical_risk = calculate_historical_delay_risk(
        supplier.historical_delay_percentage
    )
    redundancy_risk = calculate_redundancy_risk(
        supplier.alternate_route_available, supplier.is_critical_supplier
    )

    weights = {
        "mode": 0.2,
        "distance": 0.15,
        "transit": 0.15,
        "port": 0.2,
        "historical": 0.2,
        "redundancy": 0.1,
    }

    shipping_risk_score = (
        mode_risk * weights["mode"]
        + distance_risk * weights["distance"]
        + transit_risk * weights["transit"]
        + port_risk * weights["port"]
        + historical_risk * weights["historical"]
        + redundancy_risk * weights["redundancy"]
    )

    delay_probability = min(
        1.0,
        (mode_risk + transit_risk + historical_risk + port_risk) / 4.0,
    )

    if shipping_risk_score < 0.3:
        risk_level = "Low"
    elif shipping_risk_score < 0.6:
        risk_level = "Medium"
    elif shipping_risk_score < 0.8:
        risk_level = "High"
    else:
        risk_level = "Critical"

    risk_factors: list[str] = []
    recommended_actions: list[str] = []

    if port_risk >= 0.7:
        risk_factors.append("High port congestion")
        recommended_actions.append("Add alternate port")

    if not supplier.alternate_route_available:
        risk_factors.append("No alternate route")
        recommended_actions.append("Design alternate route or backup supplier")

    if historical_risk >= 0.5:
        risk_factors.append("High historical delay")
        recommended_actions.append(
            "Increase buffer stock and monitor carrier performance"
        )

    if mode_risk >= 0.6 and (supplier.shipping_mode or "").lower() == "sea":
        risk_factors.append("Slow and disruption-prone shipping mode")
        recommended_actions.append("Consider partial air freight for urgent shipments")

    if redundancy_risk >= 0.7 and supplier.is_critical_supplier:
        risk_factors.append("Single point of failure for critical material")
        recommended_actions.append("Qualify secondary supplier for critical components")

    if distance_risk >= 0.6:
        risk_factors.append("Long transport distance")
        recommended_actions.append(
            "Increase safety stock and review routing optimization"
        )

    if not risk_factors:
        risk_factors.append("No major risk drivers detected")
        recommended_actions.append(
            "Maintain current logistics plan with periodic review"
        )

    return {
        "shipping_risk_score": round(shipping_risk_score, 2),
        "risk_level": risk_level,
        "delay_probability": round(delay_probability, 2),
        "risk_factors": risk_factors,
        "recommended_actions": recommended_actions,
    }


def _normalize_agent_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "shipping_risk_score": float(raw.get("shipping_risk_score", 0.5)),
        "risk_level": str(raw.get("risk_level", "Medium")),
        "delay_probability": float(raw.get("delay_probability", 0.5)),
        "delay_risk_score": raw.get("delay_risk_score"),
        "stagnation_risk_score": raw.get("stagnation_risk_score"),
        "velocity_risk_score": raw.get("velocity_risk_score"),
        "risk_factors": list(raw.get("risk_factors", [])),
        "recommended_actions": list(raw.get("recommended_actions", [])),
        "shipment_metadata": raw.get("shipment_metadata"),
    }


def calculate_shipping_risk(supplier: ShippingSupplier, db: Session) -> dict[str, Any]:
    """Use LLM agent when available; otherwise heuristic."""
    try:
        agent_result = analyze_shipments_for_supplier(db, supplier)
        return _normalize_agent_result(agent_result)
    except Exception:
        heuristic = calculate_shipping_risk_heuristic(supplier)
        return _normalize_agent_result(heuristic)
