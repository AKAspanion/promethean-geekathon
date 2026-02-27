"""Shipping risk assessment: run agent per supplier or for all, list assessments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.shipping_risk_assessment import ShippingRiskAssessment
from app.models.shipping_supplier import ShippingSupplier
from app.schemas.shipping_risk import (
    BulkShippingRiskResult,
    ShippingRiskAssessmentOut,
    ShippingRiskResult,
)
from app.services.shipping_risk import calculate_shipping_risk

router = APIRouter(prefix="/shipping/shipping-risk", tags=["shipping"])


@router.post(
    "/{supplier_id}",
    response_model=ShippingRiskResult,
    status_code=status.HTTP_201_CREATED,
)
def run_for_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
) -> ShippingRiskResult:
    supplier = (
        db.query(ShippingSupplier).filter(ShippingSupplier.id == supplier_id).first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )

    result_dict = calculate_shipping_risk(supplier, db)

    assessment = ShippingRiskAssessment(
        supplier_id=supplier.id,
        shipping_risk_score=result_dict["shipping_risk_score"],
        risk_level=result_dict["risk_level"],
        delay_probability=result_dict["delay_probability"],
        delay_risk_score=result_dict.get("delay_risk_score"),
        stagnation_risk_score=result_dict.get("stagnation_risk_score"),
        velocity_risk_score=result_dict.get("velocity_risk_score"),
        risk_factors=result_dict["risk_factors"],
        recommended_actions=result_dict["recommended_actions"],
        shipment_metadata=result_dict.get("shipment_metadata"),
    )
    db.add(assessment)
    db.commit()

    return ShippingRiskResult(**result_dict)


@router.post("/run-all", response_model=list[BulkShippingRiskResult])
def run_for_all(db: Session = Depends(get_db)) -> list[BulkShippingRiskResult]:
    suppliers = db.query(ShippingSupplier).all()
    results: list[BulkShippingRiskResult] = []

    for supplier in suppliers:
        result_dict = calculate_shipping_risk(supplier, db)
        assessment = ShippingRiskAssessment(
            supplier_id=supplier.id,
            shipping_risk_score=result_dict["shipping_risk_score"],
            risk_level=result_dict["risk_level"],
            delay_probability=result_dict["delay_probability"],
            delay_risk_score=result_dict.get("delay_risk_score"),
            stagnation_risk_score=result_dict.get("stagnation_risk_score"),
            velocity_risk_score=result_dict.get("velocity_risk_score"),
            risk_factors=result_dict["risk_factors"],
            recommended_actions=result_dict["recommended_actions"],
            shipment_metadata=result_dict.get("shipment_metadata"),
        )
        db.add(assessment)
        results.append(
            BulkShippingRiskResult(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                result=ShippingRiskResult(**result_dict),
            )
        )

    db.commit()
    return results


@router.get("/assessments", response_model=list[ShippingRiskAssessmentOut])
def list_assessments(db: Session = Depends(get_db)) -> list[ShippingRiskAssessmentOut]:
    assessments = db.query(ShippingRiskAssessment).all()
    return [ShippingRiskAssessmentOut.model_validate(a) for a in assessments]
