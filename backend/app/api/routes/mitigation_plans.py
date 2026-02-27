from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.schemas.mitigation_plan import (
    CreateMitigationPlan,
    UpdateMitigationPlan,
    MitigationPlanResponse,
)
from app.services.mitigation_plans import get_all, get_one, create_plan, update_plan

router = APIRouter(prefix="/mitigation-plans", tags=["mitigation-plans"])


@router.get("", response_model=list[MitigationPlanResponse])
def list_plans(
    riskId: UUID | None = Query(None),
    opportunityId: UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return get_all(
        db,
        risk_id=str(riskId) if riskId else None,
        opportunity_id=str(opportunityId) if opportunityId else None,
        status=status,
    )


@router.get("/{id}", response_model=MitigationPlanResponse)
def get_plan_by_id(
    id: UUID,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    plan = get_one(db, id)
    if not plan:
        raise HTTPException(status_code=404, detail="Mitigation plan not found")
    return plan


@router.post("", response_model=MitigationPlanResponse)
def create(
    dto: CreateMitigationPlan,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return create_plan(db, dto)


@router.put("/{id}", response_model=MitigationPlanResponse)
def update(
    id: UUID,
    dto: UpdateMitigationPlan,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    plan = update_plan(db, id, dto)
    if not plan:
        raise HTTPException(status_code=404, detail="Mitigation plan not found")
    return plan
