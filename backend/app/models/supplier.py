import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    oemId = Column(
        UUID(as_uuid=True),
        ForeignKey("oems.id", ondelete="CASCADE"),
        nullable=True,
    )
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    city = Column(String, nullable=True)
    # Keep existing country while also allowing explicit ISO-style countryCode.
    country = Column(String, nullable=True)
    countryCode = Column(String, nullable=True)
    region = Column(String, nullable=True)
    commodities = Column(String, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)

    # Latest supplier-level risk score (0-100) and level, updated after each run.
    latestRiskScore = Column(Numeric(5, 2), nullable=True)
    latestRiskLevel = Column(String, nullable=True)

    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    updatedAt = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    oem = relationship("Oem", backref="suppliers")
    risks = relationship(
        "Risk",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
