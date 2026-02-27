import uuid
from datetime import date

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WorkflowRun(Base):
    """
    Represents a single full workflow run for a given OEM.

    Runs are tracked on a daily basis and we store the sequential runIndex
    for each OEM so that day 1 / day 2 / ... runs can be distinguished.
    """

    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    oemId = Column(
        UUID(as_uuid=True),
        ForeignKey("oems.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplierId = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Calendar date for the run (UTC).
    runDate = Column(Date, nullable=False, default=date.today)

    # Monotonic counter per OEM, incremented for each new run (not reset).
    runIndex = Column(Integer, nullable=False, default=1)

    metadata_ = Column("metadata", JSONB, nullable=True)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())

    oem = relationship("Oem", backref="workflow_runs")
    supplier = relationship("Supplier", backref="workflow_runs")
