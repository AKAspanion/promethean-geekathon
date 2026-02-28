from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class RegisterOem(BaseModel):
    name: str
    email: EmailStr


class LoginOem(BaseModel):
    email: EmailStr


class OemUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    location: str | None = None
    city: str | None = None
    country: str | None = None
    countryCode: str | None = None
    region: str | None = None
    commodities: str | None = None


class OemResponse(BaseModel):
    id: UUID
    name: str
    email: str
    location: str | None = None
    city: str | None = None
    country: str | None = None
    countryCode: str | None = None
    region: str | None = None
    commodities: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    oem: OemResponse
    token: str
