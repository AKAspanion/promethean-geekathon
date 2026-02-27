import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SupplierRiskAnalysis(Base):
    """
    Per-supplier risk snapshot for a given workflow run and OEM.

    This captures the numeric riskScore plus a lightweight description and
    any structured risk details needed by the UI.
    """

    __tablename__ = "supplier_risk_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

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

    supplierId = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=True,
    )

    riskScore = Column(Numeric(5, 2), nullable=False)

    # Serialized list/summary of risks for this supplier in the run.
    risks = Column(JSONB, nullable=True)

    description = Column(Text, nullable=True)

    metadata_ = Column("metadata", JSONB, nullable=True)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())

    oem = relationship("Oem", backref="supplier_risk_analysis")
    workflow_run = relationship("WorkflowRun", backref="supplier_risk_analysis")
    supplier = relationship("Supplier", backref="risk_analysis_entries")
