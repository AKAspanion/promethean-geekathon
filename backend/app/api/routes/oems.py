from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.oem import RegisterOem, LoginOem, OemResponse, TokenResponse
from app.services.oems import register_oem, login_oem

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
