import logging
from uuid import UUID
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.risk import Risk, RiskSeverity, RiskStatus
from app.models.supplier import Supplier
from app.schemas.risk import CreateRisk, UpdateRisk

logger = logging.getLogger(__name__)


def get_all(
    db: Session,
    status: str | None = None,
    severity: str | None = None,
    oem_id: str | None = None,
    source_type: str | None = None,
    supplier_id: str | None = None,
    affected_supplier: str | None = None,
) -> list[Risk]:
    q = (
        db.query(Risk)
        .options(joinedload(Risk.mitigation_plans))
        .order_by(Risk.createdAt.desc())
    )
    if status:
        q = q.filter(Risk.status == status)
    if severity:
        q = q.filter(Risk.severity == severity)
    if oem_id:
        q = q.filter(Risk.oemId == oem_id)
    if source_type:
        q = q.filter(Risk.sourceType == source_type)
    if supplier_id:
        try:
            q = q.filter(Risk.supplierId == UUID(supplier_id))
        except (ValueError, TypeError):
            pass
    if affected_supplier:
        q = q.filter(Risk.affectedSupplier == affected_supplier)
    return q.all()


def get_one(db: Session, id: UUID) -> Risk | None:
    return (
        db.query(Risk)
        .options(joinedload(Risk.mitigation_plans))
        .filter(Risk.id == id)
        .first()
    )


def create_risk(db: Session, dto: CreateRisk) -> Risk:
    affected_suppliers = (
        [dto.affectedSupplier] if getattr(dto, "affectedSupplier", None) else None
    )
    risk = Risk(
        title=dto.title,
        description=dto.description,
        severity=dto.severity or RiskSeverity.MEDIUM,
        status=dto.status or RiskStatus.DETECTED,
        sourceType=dto.sourceType,
        sourceData=dto.sourceData,
        affectedRegion=dto.affectedRegion,
        affectedSupplier=dto.affectedSupplier,
        affectedSuppliers=affected_suppliers,
        estimatedImpact=dto.estimatedImpact,
        estimatedCost=dto.estimatedCost,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def _parse_severity(v) -> RiskSeverity:
    if isinstance(v, RiskSeverity):
        return v
    if isinstance(v, str):
        try:
            return RiskSeverity(v.lower())
        except ValueError:
            pass
    return RiskSeverity.MEDIUM


_MAX_NUMERIC = Decimal("99999999.99")


def _sanitize_numeric(value) -> Decimal | None:
    if value is None:
        return None
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    # Enforce column constraint: precision 10, scale 2 -> abs(value) < 1e8
    if num > _MAX_NUMERIC:
        return _MAX_NUMERIC
    if num < -_MAX_NUMERIC:
        return -_MAX_NUMERIC
    return num


def _resolve_supplier_id(
    db: Session,
    oem_id: UUID | None,
    affected_supplier: str | list | None,
) -> tuple[UUID | None, str | None]:
    """
    Best-effort mapping from affectedSupplier (string or list from LLM)
    to a concrete Supplier row for the given OEM.

    Returns (supplier_id, normalized_supplier_name).
    """
    if not oem_id or not affected_supplier:
        return None, None

    name: str | None
    if isinstance(affected_supplier, (list, tuple)):
        name = str(affected_supplier[0]) if affected_supplier else None
    else:
        name = str(affected_supplier)

    if not name:
        return None, None

    supplier = (
        db.query(Supplier)
        .filter(Supplier.oemId == oem_id, Supplier.name == name)
        .first()
    )
    return (supplier.id if supplier else None), name


def create_risk_from_dict(
    db: Session,
    data: dict,
    agent_status_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
) -> Risk:
    oem_id = data.get("oemId")
    # Use explicit supplierId from scope (OEM-supplier pair run) when present.
    explicit_supplier_id = data.get("supplierId")
    if explicit_supplier_id is not None and not isinstance(explicit_supplier_id, UUID):
        try:
            explicit_supplier_id = UUID(str(explicit_supplier_id))
        except (ValueError, TypeError):
            explicit_supplier_id = None
    if explicit_supplier_id is not None:
        supplier_id = explicit_supplier_id
        supplier_name = data.get("supplierName") or data.get("affectedSupplier")
        if isinstance(supplier_name, (list, tuple)):
            supplier_name = str(supplier_name[0]) if supplier_name else None
        elif supplier_name is not None:
            supplier_name = str(supplier_name)
    else:
        supplier_id, supplier_name = _resolve_supplier_id(
            db,
            oem_id,
            data.get("affectedSupplier"),
        )

    raw_aff = data.get("affectedSupplier")
    suppliers_list: list[str] | None = None
    primary_name: str | None = None
    if isinstance(raw_aff, (list, tuple)):
        names = [str(x).strip() for x in raw_aff if str(x).strip()]
        suppliers_list = names or None
        primary_name = names[0] if names else None
    elif raw_aff:
        name_str = str(raw_aff).strip()
        if name_str:
            suppliers_list = [name_str]
            primary_name = name_str
    # Prefer the resolved supplier_name as the canonical label when available.
    if supplier_name:
        primary_name = supplier_name
        if suppliers_list:
            if supplier_name not in suppliers_list:
                suppliers_list.insert(0, supplier_name)
        else:
            suppliers_list = [supplier_name]

    if not supplier_id:
        logger.warning(
            "create_risk_from_dict: no supplierId resolved for risk '%s' "
            "(affectedSupplier=%s). Risk will not appear in supplier reports.",
            data.get("title", "?"),
            primary_name,
        )

    risk = Risk(
        title=data["title"],
        description=data["description"],
        severity=_parse_severity(data.get("severity")),
        status=RiskStatus.DETECTED,
        sourceType=data.get("sourceType", "unknown"),
        sourceData=data.get("sourceData"),
        affectedRegion=data.get("affectedRegion"),
        affectedSupplier=primary_name,
        affectedSuppliers=suppliers_list,
        impactDescription=data.get("impactDescription"),
        estimatedImpact=data.get("estimatedImpact"),
        estimatedCost=_sanitize_numeric(data.get("estimatedCost")),
        oemId=oem_id,
        workflowRunId=workflow_run_id,
        supplierId=supplier_id,
        agentStatusId=agent_status_id,
        metadata_=data.get("metadata"),
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def update_risk(db: Session, id: UUID, dto: UpdateRisk) -> Risk | None:
    risk = get_one(db, id)
    if not risk:
        return None
    update_data = dto.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(risk, k, v)
    db.commit()
    db.refresh(risk)
    return risk


def get_stats(db: Session) -> dict:
    total = db.query(func.count(Risk.id)).scalar() or 0
    by_status = db.query(Risk.status, func.count(Risk.id)).group_by(Risk.status).all()
    by_severity = (
        db.query(Risk.severity, func.count(Risk.id)).group_by(Risk.severity).all()
    )
    return {
        "total": total,
        "byStatus": {str(s): c for s, c in by_status},
        "bySeverity": {str(s): c for s, c in by_severity},
    }
