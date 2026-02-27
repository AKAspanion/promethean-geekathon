import uuid
import enum
from sqlalchemy import Column, String, Text, DateTime, Numeric, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OpportunityType(str, enum.Enum):
    COST_SAVING = "cost_saving"
    TIME_SAVING = "time_saving"
    QUALITY_IMPROVEMENT = "quality_improvement"
    MARKET_EXPANSION = "market_expansion"
    SUPPLIER_DIVERSIFICATION = "supplier_diversification"


class OpportunityStatus(str, enum.Enum):
    IDENTIFIED = "identified"
    EVALUATING = "evaluating"
    IMPLEMENTING = "implementing"
    REALIZED = "realized"
    EXPIRED = "expired"


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    oemId = Column(UUID(as_uuid=True), nullable=True)
    workflowRunId = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplierId = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    type = Column(
        Enum(
            OpportunityType,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="opportunities_type_enum",
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            OpportunityStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="opportunities_status_enum",
        ),
        default=OpportunityStatus.IDENTIFIED,
    )
    sourceType = Column(String, nullable=False)
    sourceData = Column(JSONB, nullable=True)
    affectedRegion = Column(String, nullable=True)
    # Optional list of all supplier names this opportunity impacts.
    affectedSuppliers = Column(JSONB, nullable=True)
    # Optional free-form human impact summary aligned with new schema.
    impactDescription = Column(Text, nullable=True)
    potentialBenefit = Column(String, nullable=True)
    estimatedValue = Column(Numeric(10, 2), nullable=True)

    agentStatusId = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_status.id", ondelete="SET NULL"),
        nullable=True,
    )

    metadata_ = Column("metadata", JSONB, nullable=True)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    mitigation_plans = relationship(
        "MitigationPlan", back_populates="opportunity", cascade="all, delete-orphan"
    )
