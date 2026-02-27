"""Shipment linked to a shipping supplier (AWB, dates, status)."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer,
        ForeignKey("shipping_suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )

    awb_code = Column(String(64), unique=True, nullable=False, index=True)
    courier_name = Column(String(255), nullable=True)

    origin_city = Column(String(255), nullable=False)
    destination_city = Column(String(255), nullable=False)

    pickup_date = Column(DateTime, nullable=False)
    expected_delivery_date = Column(DateTime, nullable=False)
    delivered_date = Column(DateTime, nullable=True)

    current_status = Column(String(100), nullable=False, default="In Transit")

    weight = Column(Float, nullable=True)
    packages = Column(Integer, nullable=True)

    supplier = relationship("ShippingSupplier", back_populates="shipments")
