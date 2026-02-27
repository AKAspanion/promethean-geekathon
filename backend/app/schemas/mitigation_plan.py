from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime, date
from app.models.mitigation_plan import PlanStatus


class CreateMitigationPlan(BaseModel):
    title: str
    description: str
    actions: list[str]
    status: PlanStatus | None = None
    riskId: UUID | None = None
    opportunityId: UUID | None = None
    metadata: dict | None = None
    assignedTo: str | None = None
    dueDate: date | None = None


class UpdateMitigationPlan(BaseModel):
    title: str | None = None
    description: str | None = None
    actions: list[str] | None = None
    status: PlanStatus | None = None
    assignedTo: str | None = None
    dueDate: date | None = None
    metadata: dict | None = None


class MitigationPlanResponse(BaseModel):
    id: UUID
    title: str
    description: str
    actions: list[str]
    status: str
    riskId: UUID | None = None
    opportunityId: UUID | None = None
    metadata_: dict | None = Field(None, serialization_alias="metadata")
    assignedTo: str | None = None
    dueDate: date | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": True}
