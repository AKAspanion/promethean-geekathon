import uuid
import enum
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from app.database import Base


def _coerce_actions_to_strings(value):
    """Ensure value is a list of strings for ARRAY(Text). Handles LLM list-of-dicts."""
    if value is None:
        return []
    if not isinstance(value, list):
        return [str(value).strip() or "—"]
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item.strip() or "—")
        elif isinstance(item, dict):
            s = item.get("action") or item.get("description") or item.get("title")
            if s is None and item:
                s = next(iter(item.values()), "—")
            out.append(str(s).strip() if s else "—")
        else:
            out.append(str(item).strip() if item else "—")
    return out


class ActionsArray(TypeDecorator):
    """ARRAY(Text) that coerces list-of-dicts from LLM to list of strings."""

    impl = ARRAY(Text)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _coerce_actions_to_strings(value)


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MitigationPlan(Base):
    __tablename__ = "mitigation_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    actions = Column(ActionsArray, nullable=False)
    status = Column(
        Enum(
            PlanStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="mitigation_plans_status_enum",
        ),
        default=PlanStatus.DRAFT,
    )
    riskId = Column(UUID(as_uuid=True), ForeignKey("risks.id"), nullable=True)
    opportunityId = Column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id"),
        nullable=True,
    )
    # Keep a loose association back to the workflow run via the agent status.
    agentStatusId = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_status.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_ = Column("metadata", JSONB, nullable=True)
    assignedTo = Column(String, nullable=True)
    dueDate = Column(Date, nullable=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    risk = relationship("Risk", back_populates="mitigation_plans")
    opportunity = relationship("Opportunity", back_populates="mitigation_plans")
