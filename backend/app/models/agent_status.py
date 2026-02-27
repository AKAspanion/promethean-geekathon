import uuid
import enum
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    MONITORING = "monitoring"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class AgentStatusEntity(Base):
    __tablename__ = "agent_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # High-level identifiers for this status row.
    oemId = Column(
        UUID(as_uuid=True),
        ForeignKey("oems.id", ondelete="CASCADE"),
        nullable=True,
    )
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

    status = Column(String, default=AgentStatus.IDLE.value)
    currentTask = Column(Text, nullable=True)
    lastProcessedData = Column(JSONB, nullable=True)
    lastDataSource = Column(String, nullable=True)
    errorMessage = Column(String, nullable=True)
    risksDetected = Column(Integer, default=0)
    opportunitiesIdentified = Column(Integer, default=0)
    plansGenerated = Column(Integer, default=0)
    metadata_ = Column("metadata", JSONB, nullable=True)
    lastUpdated = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
