from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.opportunity import OpportunityType, OpportunityStatus


class CreateOpportunity(BaseModel):
    title: str
    description: str
    type: OpportunityType
    status: OpportunityStatus | None = None
    sourceType: str
    sourceData: dict | None = None
    affectedRegion: str | None = None
    potentialBenefit: str | None = None
    estimatedValue: Decimal | None = None


class UpdateOpportunity(BaseModel):
    title: str | None = None
    description: str | None = None
    type: OpportunityType | None = None
    status: OpportunityStatus | None = None
    affectedRegion: str | None = None
    potentialBenefit: str | None = None
    estimatedValue: Decimal | None = None


class MitigationPlanRef(BaseModel):
    id: UUID
    title: str
    status: str

    model_config = {"from_attributes": True}


class OpportunityResponse(BaseModel):
    id: UUID
    title: str
    description: str
    type: str
    status: str
    sourceType: str
    sourceData: dict | None = None
    affectedRegion: str | None = None
    potentialBenefit: str | None = None
    estimatedValue: Decimal | None = None
    oemId: UUID | None = None
    mitigation_plans: list[MitigationPlanRef] | None = Field(
        None, serialization_alias="mitigationPlans"
    )
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": True}
