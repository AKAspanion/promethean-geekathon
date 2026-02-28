from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.oem import Oem
from app.schemas.oem import RegisterOem
from app.api.deps import create_access_token


def get_oem_by_id(db: Session, oem_id: UUID) -> Oem | None:
    return db.query(Oem).filter(Oem.id == oem_id).first()


def get_oem_by_email(db: Session, email: str) -> Oem | None:
    normalized = email.strip().lower()
    return db.query(Oem).filter(Oem.email == normalized).first()


def register_oem(db: Session, dto: RegisterOem) -> tuple[Oem, str]:
    existing = get_oem_by_email(db, dto.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An OEM with this email is already registered.",
        )
    oem = Oem(
        name=dto.name.strip(),
        email=dto.email.strip().lower(),
    )
    db.add(oem)
    db.commit()
    db.refresh(oem)
    token = create_access_token(oem.id, oem.email)
    return oem, token


def login_oem(db: Session, email: str) -> tuple[Oem, str]:
    normalized = email.strip().lower()
    oem = get_oem_by_email(db, normalized)
    if not oem:
        oem = Oem(
            name=normalized.split("@")[0],
            email=normalized,
        )
        db.add(oem)
        db.commit()
        db.refresh(oem)
    token = create_access_token(oem.id, oem.email)
    return oem, token


def get_all_oems(db: Session) -> list[Oem]:
    return db.query(Oem).order_by(Oem.createdAt.asc()).all()


def update_oem(db: Session, oem_id: UUID, data: dict) -> Oem | None:
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        return None
    if "email" in data and data["email"]:
        normalized = data["email"].strip().lower()
        existing = get_oem_by_email(db, normalized)
        if existing and existing.id != oem_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An OEM with this email is already registered.",
            )
        data["email"] = normalized
    for key, value in data.items():
        if value is not None:
            setattr(oem, key, value)
    db.commit()
    db.refresh(oem)
    return oem


def delete_oem(db: Session, oem_id: UUID) -> bool:
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        return False
    db.delete(oem)
    db.commit()
    return True
