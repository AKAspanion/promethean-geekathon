from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.risk import RiskSeverity, RiskStatus


class CreateRisk(BaseModel):
    title: str
    description: str
    severity: RiskSeverity | None = None
    status: RiskStatus | None = None
    sourceType: str
    sourceData: dict | None = None
    affectedRegion: str | None = None
    affectedSupplier: str | None = None
    estimatedImpact: str | None = None
    estimatedCost: Decimal | None = None


class UpdateRisk(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: RiskSeverity | None = None
    status: RiskStatus | None = None
    affectedRegion: str | None = None
    affectedSupplier: str | None = None
    estimatedImpact: str | None = None
    estimatedCost: Decimal | None = None


class MitigationPlanRef(BaseModel):
    id: UUID
    title: str
    status: str

    model_config = {"from_attributes": True}


class RiskResponse(BaseModel):
    id: UUID
    title: str
    description: str
    severity: str
    status: str
    sourceType: str
    sourceData: dict | None = None
    affectedRegion: str | None = None
    affectedSupplier: str | None = None
    estimatedImpact: str | None = None
    estimatedCost: Decimal | None = None
    oemId: UUID | None = None
    supplierId: UUID | None = None
    mitigation_plans: list[MitigationPlanRef] | None = Field(
        None, serialization_alias="mitigationPlans"
    )
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": True}
