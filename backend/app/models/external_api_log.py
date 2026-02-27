import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class ExternalApiLog(Base):
    __tablename__ = "external_api_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service = Column(String, nullable=True)
    method = Column(String, nullable=False, default="GET")
    url = Column(Text, nullable=False)
    params = Column(JSONB, nullable=True)
    statusCode = Column(Integer, nullable=True)
    fromCache = Column(Boolean, nullable=False, default=False)
    elapsedMs = Column(Integer, nullable=True)
    requestHeaders = Column(JSONB, nullable=True)
    responseBody = Column(JSONB, nullable=True)
    errorMessage = Column(Text, nullable=True)
    createdAt = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
