import uuid
from sqlalchemy import Column, String, Float, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class TrendInsight(Base):
    __tablename__ = "trend_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Scope metadata
    scope = Column(String, nullable=False)  # material | supplier | global
    entity_name = Column(
        String, nullable=True
    )  # supplier name, material name, or "Global"
    risk_opportunity = Column(
        String, nullable=False, default="risk"
    )  # risk | opportunity

    # Insight content
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    predicted_impact = Column(Text, nullable=True)
    time_horizon = Column(String, nullable=True)  # short-term | medium-term | long-term
    severity = Column(String, nullable=True)  # low | medium | high | critical
    recommended_actions = Column(JSONB, nullable=True)  # list[str]
    source_articles = Column(JSONB, nullable=True)  # list[str]
    confidence = Column(Float, nullable=True)

    # Run provenance
    oem_name = Column(String, nullable=True)
    excel_path = Column(String, nullable=True)
    llm_provider = Column(String, nullable=True)

    createdAt = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
