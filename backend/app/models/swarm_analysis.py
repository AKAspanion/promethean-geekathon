import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SwarmAnalysis(Base):
    """
    LLM-generated swarm analysis linked 1:1 to a SupplierRiskAnalysis row.

    Stores the per-agent breakdown, top drivers, and mitigation plan
    so the API can read persisted data instead of computing on-the-fly.
    """

    __tablename__ = "swarm_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    supplierRiskAnalysisId = Column(
        UUID(as_uuid=True),
        ForeignKey("supplier_risk_analysis.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    supplierId = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )

    oemId = Column(
        UUID(as_uuid=True),
        ForeignKey("oems.id", ondelete="CASCADE"),
        nullable=False,
    )

    workflowRunId = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    finalScore = Column(Numeric(5, 2), nullable=False)
    riskLevel = Column(String(20), nullable=False)
    topDrivers = Column(JSONB, nullable=False)
    mitigationPlan = Column(JSONB, nullable=False)
    agents = Column(JSONB, nullable=False)

    llmRawResponse = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())

    supplier_risk_analysis = relationship(
        "SupplierRiskAnalysis", backref="swarm_analysis", uselist=False
    )
    supplier = relationship("Supplier", backref="swarm_analyses")
    oem = relationship("Oem", backref="swarm_analyses")
    workflow_run = relationship("WorkflowRun", backref="swarm_analyses")
