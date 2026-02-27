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
    get_swarm_summaries_by_supplier,
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
    swarm_map = get_swarm_summaries_by_supplier(db, oem.id)
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
            # Swarm Controller style per-supplier output derived from existing risks
            "swarm": swarm_map.get(s.name),
        }
        for s in suppliers
    ]


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
    swarm_map = get_swarm_summaries_by_supplier(db, oem.id)
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
        "swarm": swarm_map.get(supplier.name),
    }


def _format_supplier(supplier, risk_map, swarm_map):
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
        "swarm": swarm_map.get(supplier.name),
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
    swarm_map = get_swarm_summaries_by_supplier(db, oem.id)
    return _format_supplier(supplier, risk_map, swarm_map)


@router.delete("/{id}", status_code=204)
def delete_supplier(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    deleted = delete_one(db, id, oem.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")
