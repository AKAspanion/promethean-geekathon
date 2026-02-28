from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.schemas.oem import RegisterOem, LoginOem, OemUpdate, OemResponse, TokenResponse
from app.services.oems import register_oem, login_oem, update_oem, delete_oem

router = APIRouter(prefix="/oems", tags=["oems"])


@router.post("/register", response_model=TokenResponse)
def register(
    dto: RegisterOem,
    db: Session = Depends(get_db),
):
    oem, token = register_oem(db, dto)
    return TokenResponse(oem=OemResponse.model_validate(oem), token=token)


@router.post("/login", response_model=TokenResponse)
def login(
    dto: LoginOem,
    db: Session = Depends(get_db),
):
    oem, token = login_oem(db, dto.email)
    return TokenResponse(oem=OemResponse.model_validate(oem), token=token)


@router.get("/me", response_model=OemResponse)
def get_profile(
    oem: Oem = Depends(get_current_oem),
):
    return OemResponse.model_validate(oem)


@router.put("/me", response_model=OemResponse)
def update_profile(
    body: OemUpdate,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = update_oem(db, oem.id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="OEM not found")
    return OemResponse.model_validate(updated)


@router.delete("/me", status_code=204)
def delete_profile(
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    deleted = delete_oem(db, oem.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="OEM not found")
