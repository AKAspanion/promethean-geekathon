"""CRUD for shipping suppliers (list, get, create, update, delete)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.models.shipping_supplier import ShippingSupplier
from app.schemas.shipping_supplier import ShippingSupplierCreate, ShippingSupplierUpdate


def get_suppliers(
    db: Session, skip: int = 0, limit: int = 100
) -> Sequence[ShippingSupplier]:
    return db.query(ShippingSupplier).offset(skip).limit(limit).all()


def get_supplier(db: Session, supplier_id: int) -> ShippingSupplier | None:
    return db.query(ShippingSupplier).filter(ShippingSupplier.id == supplier_id).first()


def create_supplier(db: Session, data: ShippingSupplierCreate) -> ShippingSupplier:
    supplier = ShippingSupplier(**data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(
    db: Session, supplier: ShippingSupplier, data: ShippingSupplierUpdate
) -> ShippingSupplier:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(db: Session, supplier: ShippingSupplier) -> None:
    db.delete(supplier)
    db.commit()
