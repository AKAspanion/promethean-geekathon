from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ShippingRiskAssessmentOut(BaseModel):
    id: int
    supplier_id: int
    shipping_risk_score: float
    risk_level: str
    delay_probability: float
    delay_risk_score: float | None = None
    stagnation_risk_score: float | None = None
    velocity_risk_score: float | None = None
    risk_factors: list[str]
    recommended_actions: list[str]
    shipment_metadata: dict[str, Any] | None = None
    assessed_at: datetime

    model_config = {"from_attributes": True}


class ShippingRiskResult(BaseModel):
    shipping_risk_score: float
    risk_level: str
    delay_probability: float
    delay_risk_score: float | None = None
    stagnation_risk_score: float | None = None
    velocity_risk_score: float | None = None
    risk_factors: list[str]
    recommended_actions: list[str]
    shipment_metadata: dict[str, Any] | None = None


class BulkShippingRiskResult(BaseModel):
    supplier_id: int
    supplier_name: str
    result: ShippingRiskResult
