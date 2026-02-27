import uuid

from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class LlmLog(Base):
    __tablename__ = "llm_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    callId = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="success")
    errorMessage = Column(Text, nullable=True)
    elapsedMs = Column(Integer, nullable=True)
    createdAt = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
