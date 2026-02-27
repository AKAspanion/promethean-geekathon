from typing import NotRequired, TypedDict


class OemScope(TypedDict):
    """Scope for workflow: OEM + optional single supplier (for OEM-supplier pair runs)."""

    oemId: str
    oemName: str
    supplierNames: list[str]
    locations: list[str]
    cities: list[str]
    countries: list[str]
    regions: list[str]
    commodities: list[str]
    # When workflow runs per OEM-supplier pair, these identify the supplier.
    supplierId: str
    supplierName: str
