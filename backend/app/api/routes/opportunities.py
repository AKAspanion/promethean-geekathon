from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.schemas.opportunity import (
    CreateOpportunity,
    UpdateOpportunity,
    OpportunityResponse,
)
from app.services.opportunities import (
    get_all,
    get_one,
    create_opportunity,
    update_opportunity,
    get_stats,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("/stats/summary")
def opportunity_stats(db: Session = Depends(get_db), _: Oem = Depends(get_current_oem)):
    return get_stats(db)


@router.get("", response_model=list[OpportunityResponse])
def list_opportunities(
    status: str | None = Query(None),
    type: str | None = Query(None),
    oemId: str | None = Query(None),
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return get_all(db, status=status, type=type, oem_id=oemId)


@router.get("/{id}", response_model=OpportunityResponse)
def get_opportunity_by_id(
    id: UUID,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    opp = get_one(db, id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@router.post("", response_model=OpportunityResponse)
def create(
    dto: CreateOpportunity,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    return create_opportunity(db, dto)


@router.put("/{id}", response_model=OpportunityResponse)
def update(
    id: UUID,
    dto: UpdateOpportunity,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    opp = update_opportunity(db, id, dto)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp
