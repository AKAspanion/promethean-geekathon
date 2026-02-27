import uuid
from sqlalchemy import Column, String, Text, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class SupplyChainRiskScore(Base):
    __tablename__ = "supply_chain_risk_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    oemId = Column("oem_id", UUID(as_uuid=True), nullable=False)
    workflowRunId = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    overallScore = Column("overall_score", Numeric(5, 2), nullable=False)
    breakdown = Column(JSONB, nullable=True)
    severityCounts = Column(JSONB, nullable=True)
    riskIds = Column(String, nullable=True)  # simple-array stored as comma-separated
    summary = Column(Text, nullable=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
