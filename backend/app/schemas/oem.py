from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class RegisterOem(BaseModel):
    name: str
    email: EmailStr


class LoginOem(BaseModel):
    email: EmailStr


class OemResponse(BaseModel):
    id: UUID
    name: str
    email: str
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    oem: OemResponse
    token: str
