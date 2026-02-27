"""Shipping intelligence suppliers (list, get, create, update, delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.shipping_supplier import (
    ShippingSupplierCreate,
    ShippingSupplierOut,
    ShippingSupplierUpdate,
)
from app.services.shipping_suppliers_crud import (
    create_supplier,
    delete_supplier,
    get_supplier,
    get_suppliers,
    update_supplier,
)

router = APIRouter(prefix="/shipping/suppliers", tags=["shipping"])


@router.post(
    "/", response_model=ShippingSupplierOut, status_code=status.HTTP_201_CREATED
)
def create(
    data: ShippingSupplierCreate,
    db: Session = Depends(get_db),
) -> ShippingSupplierOut:
    supplier = create_supplier(db, data)
    return ShippingSupplierOut.model_validate(supplier)


@router.get("/", response_model=list[ShippingSupplierOut])
def list_suppliers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[ShippingSupplierOut]:
    suppliers = get_suppliers(db, skip=skip, limit=limit)
    return [ShippingSupplierOut.model_validate(s) for s in suppliers]


@router.get("/{supplier_id}", response_model=ShippingSupplierOut)
def get_one(
    supplier_id: int,
    db: Session = Depends(get_db),
) -> ShippingSupplierOut:
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    return ShippingSupplierOut.model_validate(supplier)


@router.put("/{supplier_id}", response_model=ShippingSupplierOut)
def update(
    supplier_id: int,
    data: ShippingSupplierUpdate,
    db: Session = Depends(get_db),
) -> ShippingSupplierOut:
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    updated = update_supplier(db, supplier, data)
    return ShippingSupplierOut.model_validate(updated)


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete(
    supplier_id: int,
    db: Session = Depends(get_db),
) -> None:
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    delete_supplier(db, supplier)
