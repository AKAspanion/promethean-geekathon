from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.oem import Oem

security = HTTPBearer(auto_error=False)


def create_access_token(oem_id: UUID, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.jwt_expire_days)
    to_encode = {"sub": str(oem_id), "email": email, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )


async def get_current_oem(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> Oem:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    payload = decode_token(credentials.credentials)
    oem_id = payload.get("sub")
    if not oem_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    from app.services.oems import get_oem_by_id

    oem = get_oem_by_id(db, UUID(oem_id))
    if not oem:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OEM not found",
        )
    return oem
