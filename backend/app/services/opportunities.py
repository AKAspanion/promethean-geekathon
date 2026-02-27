from uuid import UUID
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.opportunity import Opportunity, OpportunityType, OpportunityStatus
from app.schemas.opportunity import CreateOpportunity, UpdateOpportunity


_MAX_NUMERIC = Decimal("99999999.99")


def _sanitize_numeric(value) -> Decimal | None:
    if value is None:
        return None
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if num > _MAX_NUMERIC:
        return _MAX_NUMERIC
    if num < -_MAX_NUMERIC:
        return -_MAX_NUMERIC
    return num


def get_all(
    db: Session,
    status: str | None = None,
    type: str | None = None,
    oem_id: str | None = None,
) -> list[Opportunity]:
    q = (
        db.query(Opportunity)
        .options(joinedload(Opportunity.mitigation_plans))
        .order_by(Opportunity.createdAt.desc())
    )
    if status:
        q = q.filter(Opportunity.status == status)
    if type:
        q = q.filter(Opportunity.type == type)
    if oem_id:
        q = q.filter(Opportunity.oemId == oem_id)
    return q.all()


def get_one(db: Session, id: UUID) -> Opportunity | None:
    return (
        db.query(Opportunity)
        .options(joinedload(Opportunity.mitigation_plans))
        .filter(Opportunity.id == id)
        .first()
    )


def create_opportunity(db: Session, dto: CreateOpportunity) -> Opportunity:
    opp = Opportunity(
        title=dto.title,
        description=dto.description,
        type=dto.type,
        status=dto.status or OpportunityStatus.IDENTIFIED,
        sourceType=dto.sourceType,
        sourceData=dto.sourceData,
        affectedRegion=dto.affectedRegion,
        potentialBenefit=dto.potentialBenefit,
        estimatedValue=dto.estimatedValue,
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def create_opportunity_from_dict(
    db: Session,
    data: dict,
    agent_status_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
) -> Opportunity:
    type_val = data.get("type", "cost_saving")
    if isinstance(type_val, str):
        try:
            type_enum = OpportunityType(type_val)
        except ValueError:
            type_enum = OpportunityType.COST_SAVING
    else:
        type_enum = type_val
    opp = Opportunity(
        title=data["title"],
        description=data["description"],
        type=type_enum,
        status=OpportunityStatus.IDENTIFIED,
        sourceType=data.get("sourceType", "unknown"),
        sourceData=data.get("sourceData"),
        affectedRegion=data.get("affectedRegion"),
        affectedSuppliers=data.get("affectedSuppliers"),
        impactDescription=data.get("impactDescription"),
        potentialBenefit=data.get("potentialBenefit"),
        estimatedValue=_sanitize_numeric(data.get("estimatedValue")),
        oemId=data.get("oemId"),
        workflowRunId=workflow_run_id,
        supplierId=data.get("supplierId"),
        agentStatusId=agent_status_id,
        metadata_=data.get("metadata"),
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def update_opportunity(
    db: Session, id: UUID, dto: UpdateOpportunity
) -> Opportunity | None:
    opp = get_one(db, id)
    if not opp:
        return None
    update_data = dto.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(opp, k, v)
    db.commit()
    db.refresh(opp)
    return opp


def get_stats(db: Session) -> dict:
    total = db.query(func.count(Opportunity.id)).scalar() or 0
    by_status = (
        db.query(Opportunity.status, func.count(Opportunity.id))
        .group_by(Opportunity.status)
        .all()
    )
    by_type = (
        db.query(Opportunity.type, func.count(Opportunity.id))
        .group_by(Opportunity.type)
        .all()
    )
    return {
        "total": total,
        "byStatus": {str(s): c for s, c in by_status},
        "byType": {str(t): c for t, c in by_type},
    }
