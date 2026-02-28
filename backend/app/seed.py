"""Seed OEMs, suppliers, and shipping data if empty. Call from startup or manually."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models.oem import Oem
from app.models.shipment import Shipment
from app.models.shipping_supplier import ShippingSupplier
from app.models.supplier import Supplier

# OEMs to seed (id, name, email, optional location fields)
SEED_OEMS = [
    {
        "id": UUID("1cf64011-88f8-4e71-85dd-e3e9a4c0d3df"),
        "name": "ankitp",
        "email": "ankitp@geekyants.com",
        "location": "Kolkata",
        "city": "Kolkata",
        "country": "India",
        "countryCode": "IN",
        "region": "Asia",
        "commodities": "Semiconductor Chips",
        "metadata_": {
            "Tier": "1",
            "Contact Email": "ankitp@geekyants.com",
            "Primary Contact": "Ankit Pandit",
        },
    },
    {
        "id": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Geek Electronics",
        "email": "test@test.com",
        "location": "Kolkata",
        "city": "Kolkata",
        "country": "India",
        "countryCode": "IN",
        "region": None,
        "commodities": "Semiconductor Chips",
        "metadata_": {
            "Tier": "1",
            "Contact Email": "test@test.com",
            "Primary Contact": "Test User",
        },
    },
]

# Suppliers to seed (all linked to OEM 9c682575-0285-437f-a1e5-fdba3128fbf5)
SEED_SUPPLIERS = [
    {
        "id": UUID("34782817-67fc-4500-995f-33ed83845570"),
        "oemId": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Northstar Plastics Inc.",
        "location": "4500 Industrial Park",
        "city": "Detroit",
        "country": "USA",
        "countryCode": "USA",
        "region": "North America",
        "commodities": "Plastic housings; Connectors",
        "metadata_": {
            "Tier": "2",
            "Contact Email": "mark.johnson@northstarplastics.com",
            "Primary Contact": "Mark Johnson",
            "Lead Time (days)": "20",
        },
        "latestRiskScore": None,
        "latestRiskLevel": None,
    },
    {
        "id": UUID("5d935889-7558-4e72-ba73-a772dd30f666"),
        "oemId": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Zenith Electronics Sdn Bhd",
        "location": "Lot 22 Tech Park",
        "city": "Penang",
        "country": "Malaysia",
        "countryCode": "Malaysia",
        "region": "APAC",
        "commodities": "PCBs; Electronic assemblies",
        "metadata_": {
            "Tier": "1",
            "Contact Email": "ahmad.rahman@zenith-elec.my",
            "Primary Contact": "Ahmad Rahman",
            "Lead Time (days)": "28",
        },
        "latestRiskScore": None,
        "latestRiskLevel": None,
    },
    {
        "id": UUID("b6a9a0e5-ff9e-4640-8a5b-37f04405b4b1"),
        "oemId": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Pacific Fasteners Co.",
        "location": "123 Harbor Road",
        "city": "Shanghai",
        "country": "China",
        "countryCode": "China",
        "region": "APAC",
        "commodities": "Fasteners; Bolts; Nuts",
        "metadata_": {
            "Tier": "1",
            "Contact Email": "li.wei@pacificfasteners.cn",
            "Primary Contact": "Li Wei",
            "Lead Time (days)": "45",
        },
        "latestRiskScore": None,
        "latestRiskLevel": None,
    },
    {
        "id": UUID("e8cbd389-5c6e-41d7-8963-ba5223a98426"),
        "oemId": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Alpha Components GmbH",
        "location": "Industriestrasse 12",
        "city": "Stuttgart",
        "country": "Germany",
        "countryCode": "Germany",
        "region": "Europe",
        "commodities": "Aluminum castings; Engine blocks",
        "metadata_": {
            "Tier": "1",
            "Contact Email": "julia.meier@alpha-components.de",
            "Primary Contact": "Julia Meier",
            "Lead Time (days)": "30",
        },
        "latestRiskScore": None,
        "latestRiskLevel": None,
    },
    {
        "id": UUID("f1a9b3e2-7d44-4c8c-9a11-55c2b5e0aa77"),
        "oemId": UUID("9c682575-0285-437f-a1e5-fdba3128fbf5"),
        "name": "Pars Industrial Metals Co.",
        "location": "No. 25 Industrial Zone",
        "city": "Bandar Abbas",
        "country": "Iran",
        "countryCode": "IR",
        "region": "Middle East",
        "commodities": "Steel billets; Industrial alloys",
        "metadata_": {
            "Tier": "2",
            "Contact Email": "info@parsmetals.ir",
            "Primary Contact": "Reza Karimi",
            "Lead Time (days)": "22",
        },
        "latestRiskScore": None,
        "latestRiskLevel": None,
    },
]


def _seed_oems(db: Session) -> None:
    """Insert seed OEMs if they do not already exist (by id)."""
    for data in SEED_OEMS:
        if db.query(Oem).filter(Oem.id == data["id"]).first() is not None:
            continue
        db.add(Oem(**data))
    db.commit()


def _seed_suppliers(db: Session) -> None:
    """Insert seed suppliers if they do not already exist (by id)."""
    for data in SEED_SUPPLIERS:
        if db.query(Supplier).filter(Supplier.id == data["id"]).first() is not None:
            continue
        db.add(Supplier(**data))
    db.commit()


def _create_shipping_seed_data(db: Session) -> None:
    suppliers = [
        ShippingSupplier(
            name="Chennai Chip Supplier",
            material_name="Semiconductor Chips",
            location_city="Chennai",
            destination_city="Bangalore",
            latitude=13.0827,
            longitude=80.2707,
            shipping_mode="Road",
            distance_km=350,
            avg_transit_days=2,
            historical_delay_percentage=5,
            port_used=None,
            alternate_route_available=False,
            is_critical_supplier=True,
        ),
        ShippingSupplier(
            name="Mumbai Electronics Ltd",
            material_name="Power Modules",
            location_city="Mumbai",
            destination_city="Bangalore",
            latitude=19.0760,
            longitude=72.8777,
            shipping_mode="Road",
            distance_km=980,
            avg_transit_days=4,
            historical_delay_percentage=25,
            port_used=None,
            alternate_route_available=True,
            is_critical_supplier=True,
        ),
        ShippingSupplier(
            name="Delhi Precision Parts",
            material_name="CNC Machined Parts",
            location_city="Delhi",
            destination_city="Bangalore",
            latitude=28.7041,
            longitude=77.1025,
            shipping_mode="Rail",
            distance_km=2150,
            avg_transit_days=5,
            historical_delay_percentage=18,
            port_used=None,
            alternate_route_available=False,
            is_critical_supplier=False,
        ),
        ShippingSupplier(
            name="Pune Motor Components",
            material_name="Motor Housings",
            location_city="Pune",
            destination_city="Bangalore",
            latitude=18.5204,
            longitude=73.8567,
            shipping_mode="Road",
            distance_km=840,
            avg_transit_days=3,
            historical_delay_percentage=8,
            port_used=None,
            alternate_route_available=True,
            is_critical_supplier=False,
        ),
        ShippingSupplier(
            name="Kolkata Steel Supplier",
            material_name="Steel Coils",
            location_city="Kolkata",
            destination_city="Bangalore",
            latitude=22.5726,
            longitude=88.3639,
            shipping_mode="Rail",
            distance_km=1900,
            avg_transit_days=6,
            historical_delay_percentage=30,
            port_used=None,
            alternate_route_available=False,
            is_critical_supplier=True,
        ),
    ]

    for s in suppliers:
        db.add(s)
    db.flush()

    def _by_name(name: str) -> ShippingSupplier:
        for sup in suppliers:
            if sup.name == name:
                return sup
        raise KeyError(name)

    now = datetime(2022, 7, 20, 12, 0, 0)

    shipments = [
        Shipment(
            supplier_id=_by_name("Chennai Chip Supplier").id,
            awb_code="AWB-CHEN-001",
            courier_name="Xpressbees Surface",
            origin_city="Chennai",
            destination_city="Bangalore",
            pickup_date=now - timedelta(days=2, hours=2),
            expected_delivery_date=now,
            delivered_date=now,
            current_status="Delivered",
            weight=0.3,
            packages=1,
        ),
        Shipment(
            supplier_id=_by_name("Mumbai Electronics Ltd").id,
            awb_code="AWB-MUM-002",
            courier_name="Bluedart",
            origin_city="Mumbai",
            destination_city="Bangalore",
            pickup_date=now - timedelta(days=10),
            expected_delivery_date=now - timedelta(days=6),
            delivered_date=now - timedelta(days=2),
            current_status="Delivered",
            weight=1.2,
            packages=3,
        ),
        Shipment(
            supplier_id=_by_name("Delhi Precision Parts").id,
            awb_code="AWB-DEL-003",
            courier_name="Delhivery",
            origin_city="Delhi",
            destination_city="Bangalore",
            pickup_date=now - timedelta(days=7),
            expected_delivery_date=now - timedelta(days=1),
            delivered_date=None,
            current_status="In Transit",
            weight=0.8,
            packages=2,
        ),
        Shipment(
            supplier_id=_by_name("Pune Motor Components").id,
            awb_code="AWB-PUN-004",
            courier_name="Ecom Express",
            origin_city="Pune",
            destination_city="Bangalore",
            pickup_date=now - timedelta(days=2),
            expected_delivery_date=now + timedelta(days=1),
            delivered_date=now - timedelta(days=1),
            current_status="Delivered",
            weight=1.0,
            packages=1,
        ),
        Shipment(
            supplier_id=_by_name("Kolkata Steel Supplier").id,
            awb_code="AWB-KOL-005",
            courier_name="Gati",
            origin_city="Kolkata",
            destination_city="Bangalore",
            pickup_date=now - timedelta(days=12),
            expected_delivery_date=now - timedelta(days=4),
            delivered_date=None,
            current_status="In Transit",
            weight=5.0,
            packages=4,
        ),
    ]

    for sh in shipments:
        db.add(sh)

    db.commit()


def seed_oems_if_empty() -> None:
    """Ensure seed OEMs exist (by id). Idempotent."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_oems(db)
    finally:
        db.close()


def seed_suppliers_if_empty() -> None:
    """Ensure seed suppliers exist (by id). Idempotent."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_suppliers(db)
    finally:
        db.close()


def seed_shipping_if_empty() -> None:
    """Create shipping tables and seed only if no shipping suppliers exist."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(ShippingSupplier).first():
            return
        _create_shipping_seed_data(db)
    finally:
        db.close()


def seed_all_if_empty() -> None:
    """Create all tables and seed OEMs, suppliers, and shipping data if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_oems(db)
        _seed_suppliers(db)
        if db.query(ShippingSupplier).first():
            return
        _create_shipping_seed_data(db)
    finally:
        db.close()
