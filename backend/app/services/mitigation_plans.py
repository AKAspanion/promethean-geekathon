from uuid import UUID
from sqlalchemy.orm import Session, joinedload

from app.models.mitigation_plan import MitigationPlan, PlanStatus
from app.schemas.mitigation_plan import CreateMitigationPlan, UpdateMitigationPlan


def get_all(
    db: Session,
    risk_id: str | None = None,
    opportunity_id: str | None = None,
    status: str | None = None,
) -> list[MitigationPlan]:
    q = (
        db.query(MitigationPlan)
        .options(
            joinedload(MitigationPlan.risk),
            joinedload(MitigationPlan.opportunity),
        )
        .order_by(MitigationPlan.createdAt.desc())
    )
    if risk_id:
        q = q.filter(MitigationPlan.riskId == risk_id)
    if opportunity_id:
        q = q.filter(MitigationPlan.opportunityId == opportunity_id)
    if status:
        q = q.filter(MitigationPlan.status == status)
    return q.all()


def get_one(db: Session, id: UUID) -> MitigationPlan | None:
    return (
        db.query(MitigationPlan)
        .options(
            joinedload(MitigationPlan.risk),
            joinedload(MitigationPlan.opportunity),
        )
        .filter(MitigationPlan.id == id)
        .first()
    )


def create_plan(db: Session, dto: CreateMitigationPlan) -> MitigationPlan:
    plan = MitigationPlan(
        title=dto.title,
        description=dto.description,
        actions=dto.actions,
        status=dto.status or PlanStatus.DRAFT,
        riskId=dto.riskId,
        opportunityId=dto.opportunityId,
        metadata_=dto.metadata,
        assignedTo=dto.assignedTo,
        dueDate=dto.dueDate,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _normalize_actions(raw: list) -> list[str]:
    """Convert actions to list of strings for ARRAY(Text). Handles LLM list-of-dicts."""
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item.strip() or "—")
        elif isinstance(item, dict):
            s = (
                item.get("action")
                or item.get("description")
                or item.get("title")
                or (list(item.values())[0] if item else "—")
            )
            out.append(str(s).strip() or "—")
        else:
            out.append(str(item).strip() or "—")
    return out


def create_plan_from_dict(
    db: Session,
    plan_data: dict,
    risk_id: UUID | None = None,
    opportunity_id: UUID | None = None,
    agent_status_id: UUID | None = None,
) -> MitigationPlan:
    due = plan_data.get("dueDate")
    if isinstance(due, str):
        from datetime import datetime

        try:
            due = datetime.strptime(due[:10], "%Y-%m-%d").date()
        except ValueError:
            due = None
    raw_actions = plan_data.get("actions") or []
    actions = _normalize_actions(raw_actions)
    plan = MitigationPlan(
        title=plan_data.get("title") or "Untitled plan",
        description=plan_data.get("description") or "",
        actions=actions,
        status=PlanStatus.DRAFT,
        riskId=risk_id,
        opportunityId=opportunity_id,
        metadata_=plan_data.get("metadata"),
        assignedTo=plan_data.get("assignedTo"),
        dueDate=due,
        agentStatusId=agent_status_id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(
    db: Session, id: UUID, dto: UpdateMitigationPlan
) -> MitigationPlan | None:
    plan = get_one(db, id)
    if not plan:
        return None
    update_data = dto.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")
    for k, v in update_data.items():
        setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    return plan
