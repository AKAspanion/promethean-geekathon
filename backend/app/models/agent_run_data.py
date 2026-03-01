import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AgentRunData(Base):
    """
    Persists the full final state of each agent graph execution.

    One row per agent type per supplier per workflow run.  The ``finalState``
    JSONB column stores the complete dict returned by the agent runner
    function (risks, opportunities, plus all intermediate computed data such
    as daily weather timelines, fetched news articles, tracking records, etc.).
    """

    __tablename__ = "agent_run_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    oemId = Column(
        UUID(as_uuid=True),
        ForeignKey("oems.id", ondelete="CASCADE"),
        nullable=False,
    )

    supplierId = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )

    workflowRunId = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    agentType = Column(
        String(50),
        nullable=False,
    )  # weather, news_supplier, news_global, shipping

    finalState = Column(JSONB, nullable=False)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())

    oem = relationship("Oem", backref="agent_run_data")
    supplier = relationship("Supplier", backref="agent_run_data")
    workflow_run = relationship("WorkflowRun", backref="agent_run_data")
