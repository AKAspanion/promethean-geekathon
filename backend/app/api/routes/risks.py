from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.schemas.risk import CreateRisk, UpdateRisk, RiskResponse
from app.services.risks import get_all, get_one, create_risk, update_risk, get_stats

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("/stats/summary")
def risk_stats(db: Session = Depends(get_db), _: Oem = Depends(get_current_oem)):
    return get_stats(db)


@router.get("", response_model=list[RiskResponse])
def list_risks(
    status: str | None = Query(None),
    severity: str | None = Query(None),
    oemId: str | None = Query(None),
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return get_all(db, status=status, severity=severity, oem_id=oemId)


@router.get("/{id}", response_model=RiskResponse)
def get_risk_by_id(
    id: UUID,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    risk = get_one(db, id)
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return risk


@router.post("", response_model=RiskResponse)
def create(
    dto: CreateRisk,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return create_risk(db, dto)


@router.put("/{id}", response_model=RiskResponse)
def update(
    id: UUID,
    dto: UpdateRisk,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    risk = update_risk(db, id, dto)
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return risk
