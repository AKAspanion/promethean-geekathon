"""Shipping risk assessment: run agent per supplier or for all suppliers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.oem import Oem
from app.models.supplier import Supplier
from app.schemas.shipping_risk import BulkShippingRiskResult, ShippingRiskResult
from app.services.agent_types import OemScope
from app.services.shipping_risk import calculate_shipping_risk

router = APIRouter(prefix="/shipping/shipping-risk", tags=["shipping"])


def _build_scope(supplier: Supplier, oem: Oem | None) -> OemScope:
    """Build OemScope from a Supplier DB row and its OEM."""
    return {
        "oemId": str(supplier.oemId) if supplier.oemId else "",
        "oemName": oem.name if oem else "",
        "supplierNames": [supplier.name],
        "locations": [supplier.location] if supplier.location else [],
        "cities": [supplier.city] if supplier.city else [],
        "countries": [supplier.country] if supplier.country else [],
        "regions": [supplier.region] if supplier.region else [],
        "commodities": (
            [c.strip() for c in supplier.commodities.split(",") if c.strip()]
            if supplier.commodities
            else []
        ),
        "supplierId": str(supplier.id),
        "supplierName": supplier.name,
    }


@router.post(
    "/{supplier_id}",
    response_model=ShippingRiskResult,
    status_code=status.HTTP_201_CREATED,
)
def run_for_supplier(
    supplier_id: str,
    db: Session = Depends(get_db),
) -> ShippingRiskResult:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )

    oem = (
        db.query(Oem).filter(Oem.id == supplier.oemId).first()
        if supplier.oemId
        else None
    )

    scope = _build_scope(supplier, oem)
    result_dict = calculate_shipping_risk(scope, db)
    return ShippingRiskResult(**result_dict)


@router.post("/run-all", response_model=list[BulkShippingRiskResult])
def run_for_all(db: Session = Depends(get_db)) -> list[BulkShippingRiskResult]:
    suppliers = db.query(Supplier).all()

    oem_ids = {str(s.oemId) for s in suppliers if s.oemId}
    oems: dict[str, Oem] = (
        {str(o.id): o for o in db.query(Oem).filter(Oem.id.in_(oem_ids)).all()}
        if oem_ids
        else {}
    )

    results: list[BulkShippingRiskResult] = []
    for supplier in suppliers:
        oem = oems.get(str(supplier.oemId)) if supplier.oemId else None
        scope = _build_scope(supplier, oem)
        result_dict = calculate_shipping_risk(scope, db)
        results.append(
            BulkShippingRiskResult(
                supplier_id=str(supplier.id),
                supplier_name=supplier.name,
                result=ShippingRiskResult(**result_dict),
            )
        )

    return results
