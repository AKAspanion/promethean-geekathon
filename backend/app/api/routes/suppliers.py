from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.services.suppliers import (
    get_all,
    get_one,
    upload_csv,
    update_one,
    delete_one,
    get_risks_by_supplier,
    get_latest_risk_analysis_by_supplier,
    get_latest_swarm_by_supplier,
    get_supplier_metrics,
    get_supplier_risk_history,
)


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    commodities: Optional[str] = None

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    if not file.file:
        raise HTTPException(
            status_code=400, detail='No file uploaded. Use form field name "file".'
        )
    content = file.file.read()
    return upload_csv(db, oem.id, content, file.filename or "upload.csv")


@router.get("")
def list_suppliers(
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    suppliers = get_all(db, oem.id)
    risk_map = get_risks_by_supplier(db)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return [
        {
            **{
                "id": str(s.id),
                "oemId": str(s.oemId) if s.oemId else None,
                "name": s.name,
                "location": s.location,
                "city": s.city,
                "country": s.country,
                "region": s.region,
                "commodities": s.commodities,
                "metadata": s.metadata_,
                "latestRiskScore": float(s.latestRiskScore)
                if s.latestRiskScore is not None
                else None,
                "latestRiskLevel": s.latestRiskLevel,
                "createdAt": s.createdAt.isoformat() if s.createdAt else None,
                "updatedAt": s.updatedAt.isoformat() if s.updatedAt else None,
            },
            "riskSummary": risk_map.get(
                s.name,
                {"count": 0, "bySeverity": {}, "latest": None},
            ),
            "aiReasoning": reasoning_map.get(s.id),
            "swarm": swarm_map.get(s.id),
        }
        for s in suppliers
    ]


@router.get("/{id}/history")
def supplier_history(
    id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    """Risk analysis history for a supplier across workflow runs."""
    supplier = get_one(db, id, oem.id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return get_supplier_risk_history(db, id, oem.id, limit=limit)


@router.get("/{id}/metrics")
def supplier_metrics(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    """Full supplier metrics scoped to the latest workflow run."""
    supplier = get_one(db, id, oem.id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    metrics = get_supplier_metrics(db, id, oem.id)
    if not metrics:
        return {
            "supplier": {
                "id": str(supplier.id),
                "name": supplier.name,
            },
            "workflowRun": None,
            "riskAnalysis": None,
            "risks": [],
            "risksSummary": {"total": 0, "bySeverity": {}},
            "opportunities": [],
            "swarmAnalysis": None,
            "supplyChainScore": None,
            "mitigationPlans": [],
        }
    return {
        "supplier": {
            "id": str(supplier.id),
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "latestRiskScore": float(supplier.latestRiskScore) if supplier.latestRiskScore is not None else None,
            "latestRiskLevel": supplier.latestRiskLevel,
        },
        **metrics,
    }


@router.get("/{id}")
def get_supplier_by_id(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    supplier = get_one(db, id, oem.id)
    if not supplier:
        return None
    risk_map = get_risks_by_supplier(db)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return {
        **{
            "id": str(supplier.id),
            "oemId": str(supplier.oemId) if supplier.oemId else None,
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "metadata": supplier.metadata_,
            "latestRiskScore": float(supplier.latestRiskScore)
            if supplier.latestRiskScore is not None
            else None,
            "latestRiskLevel": supplier.latestRiskLevel,
            "createdAt": supplier.createdAt.isoformat() if supplier.createdAt else None,
            "updatedAt": supplier.updatedAt.isoformat() if supplier.updatedAt else None,
        },
        "riskSummary": risk_map.get(
            supplier.name,
            {"count": 0, "bySeverity": {}, "latest": None},
        ),
        "aiReasoning": reasoning_map.get(supplier.id),
        "swarm": swarm_map.get(supplier.id),
    }


def _format_supplier(supplier, risk_map, swarm_map, reasoning_map=None):
    return {
        **{
            "id": str(supplier.id),
            "oemId": str(supplier.oemId) if supplier.oemId else None,
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "metadata": supplier.metadata_,
            "latestRiskScore": float(supplier.latestRiskScore)
            if supplier.latestRiskScore is not None
            else None,
            "latestRiskLevel": supplier.latestRiskLevel,
            "createdAt": supplier.createdAt.isoformat() if supplier.createdAt else None,
            "updatedAt": supplier.updatedAt.isoformat() if supplier.updatedAt else None,
        },
        "riskSummary": risk_map.get(
            supplier.name,
            {"count": 0, "bySeverity": {}, "latest": None},
        ),
        "aiReasoning": (reasoning_map or {}).get(supplier.id),
        "swarm": swarm_map.get(supplier.id),
    }


@router.put("/{id}")
def update_supplier(
    id: UUID,
    body: SupplierUpdate,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    supplier = update_one(db, id, oem.id, data)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    risk_map = get_risks_by_supplier(db)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return _format_supplier(supplier, risk_map, swarm_map, reasoning_map)


@router.delete("/{id}", status_code=204)
def delete_supplier(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    deleted = delete_one(db, id, oem.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")
