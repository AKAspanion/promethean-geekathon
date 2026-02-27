from datetime import datetime

from pydantic import BaseModel, Field


class ShippingSupplierBase(BaseModel):
    name: str = Field(..., description="Supplier name")
    material_name: str = Field(..., description="Material or part supplied")
    location_city: str | None = Field(None, description="Origin city of supplier")
    destination_city: str = Field("Bangalore", description="Destination OEM city")

    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    shipping_mode: str = Field(..., description="e.g. Sea, Air, Road, Rail")
    distance_km: float | None = Field(None, ge=0)
    avg_transit_days: float | None = Field(None, ge=0)

    historical_delay_percentage: float | None = Field(None, ge=0, le=100)
    port_used: str | None = None

    alternate_route_available: bool = False
    is_critical_supplier: bool = False


class ShippingSupplierCreate(ShippingSupplierBase):
    pass


class ShippingSupplierUpdate(BaseModel):
    name: str | None = None
    material_name: str | None = None
    location_city: str | None = None
    destination_city: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    shipping_mode: str | None = None
    distance_km: float | None = Field(None, ge=0)
    avg_transit_days: float | None = Field(None, ge=0)
    historical_delay_percentage: float | None = Field(None, ge=0, le=100)
    port_used: str | None = None
    alternate_route_available: bool | None = None
    is_critical_supplier: bool | None = None


class ShippingSupplierOut(ShippingSupplierBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
