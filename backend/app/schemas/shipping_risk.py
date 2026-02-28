from typing import Any

from pydantic import BaseModel


class ShippingRiskResult(BaseModel):
    shipping_risk_score: float
    risk_level: str
    delay_risk: dict[str, Any] | None = None
    stagnation_risk: dict[str, Any] | None = None
    velocity_risk: dict[str, Any] | None = None
    risk_factors: list[str]
    recommended_actions: list[str]
    shipment_metadata: dict[str, Any] | None = None


class BulkShippingRiskResult(BaseModel):
    supplier_id: str  # UUID
    supplier_name: str
    result: ShippingRiskResult
