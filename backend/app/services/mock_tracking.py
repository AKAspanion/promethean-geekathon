"""Mock shipment tracking data for known AWB codes (Shiprocket-style structure)."""

from __future__ import annotations

from typing import Any


def _base_tracking(
    *,
    awb_code: str,
    origin: str,
    destination: str,
    courier_name: str,
    pickup_date: str,
    delivered_date: str | None,
    current_status: str,
    activities: list[dict[str, Any]],
    etd: str | None,
) -> dict[str, Any]:
    return {
        "tracking_data": {
            "track_status": 1,
            "shipment_status": 7 if current_status == "Delivered" else 5,
            "shipment_track": [
                {
                    "id": 1,
                    "awb_code": awb_code,
                    "courier_company_id": 51,
                    "shipment_id": 1,
                    "order_id": 1,
                    "pickup_date": pickup_date,
                    "delivered_date": delivered_date,
                    "weight": "0.30",
                    "packages": 1,
                    "current_status": current_status,
                    "delivered_to": destination,
                    "destination": destination,
                    "consignee_name": "",
                    "origin": origin,
                    "courier_agent_details": None,
                    "courier_name": courier_name,
                    "edd": None,
                    "pod": "Available" if delivered_date else None,
                    "pod_status": "https://example.com/pod.png"
                    if delivered_date
                    else None,
                }
            ],
            "shipment_track_activities": activities,
            "track_url": f"https://mock-tracking.local/{awb_code}",
            "etd": etd,
            "qc_response": {"qc_image": "", "qc_failed_reason": ""},
        }
    }


AWB_CHEN_001 = _base_tracking(
    awb_code="AWB-CHEN-001",
    origin="Chennai",
    destination="Bangalore",
    courier_name="Xpressbees Surface",
    pickup_date="2022-07-18 10:00:00",
    delivered_date="2022-07-20 15:30:00",
    current_status="Delivered",
    etd="2022-07-20 23:59:00",
    activities=[
        {
            "date": "2022-07-20 15:30:00",
            "status": "DLVD",
            "activity": "Delivered",
            "location": "BANGALORE, KARNATAKA",
            "sr-status": "7",
            "sr-status-label": "DELIVERED",
        },
        {
            "date": "2022-07-20 08:15:00",
            "status": "OFD",
            "activity": "Out for Delivery",
            "location": "BANGALORE, KARNATAKA",
            "sr-status": "17",
            "sr-status-label": "OUT FOR DELIVERY",
        },
        {
            "date": "2022-07-19 21:00:00",
            "status": "RAD",
            "activity": "Reached at Destination Hub",
            "location": "BANGALORE HUB, KARNATAKA",
            "sr-status": "38",
            "sr-status-label": "REACHED AT DESTINATION HUB",
        },
        {
            "date": "2022-07-19 10:00:00",
            "status": "IT",
            "activity": "InTransit from Chennai",
            "location": "CHENNAI, TAMIL NADU",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-18 20:00:00",
            "status": "PKD",
            "activity": "Picked from shipper",
            "location": "CHENNAI, TAMIL NADU",
            "sr-status": "6",
            "sr-status-label": "SHIPPED",
        },
    ],
)

AWB_MUM_002 = _base_tracking(
    awb_code="AWB-MUM-002",
    origin="Mumbai",
    destination="Bangalore",
    courier_name="Bluedart",
    pickup_date="2022-07-10 09:00:00",
    delivered_date="2022-07-18 16:00:00",
    current_status="Delivered",
    etd="2022-07-12 23:59:00",
    activities=[
        {
            "date": "2022-07-18 16:00:00",
            "status": "DLVD",
            "activity": "Delivered",
            "location": "BANGALORE, KARNATAKA",
            "sr-status": "7",
            "sr-status-label": "DELIVERED",
        },
        {
            "date": "2022-07-16 09:30:00",
            "status": "RAD",
            "activity": "Reached at Destination Hub",
            "location": "BANGALORE HUB, KARNATAKA",
            "sr-status": "38",
            "sr-status-label": "REACHED AT DESTINATION HUB",
        },
        {
            "date": "2022-07-13 11:00:00",
            "status": "IT",
            "activity": "InTransit - delayed at Pune hub",
            "location": "PUNE, MAHARASHTRA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-11 08:00:00",
            "status": "IT",
            "activity": "InTransit from Mumbai",
            "location": "MUMBAI, MAHARASHTRA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-10 19:00:00",
            "status": "PKD",
            "activity": "Picked from shipper",
            "location": "MUMBAI, MAHARASHTRA",
            "sr-status": "6",
            "sr-status-label": "SHIPPED",
        },
    ],
)

AWB_DEL_003 = _base_tracking(
    awb_code="AWB-DEL-003",
    origin="Delhi",
    destination="Bangalore",
    courier_name="Delhivery",
    pickup_date="2022-07-05 10:00:00",
    delivered_date=None,
    current_status="In Transit",
    etd="2022-07-10 23:59:00",
    activities=[
        {
            "date": "2022-07-08 08:00:00",
            "status": "IT",
            "activity": "InTransit - arrived at Nagpur hub",
            "location": "NAGPUR, MAHARASHTRA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-07 14:00:00",
            "status": "IT",
            "activity": "InTransit from Delhi",
            "location": "GWALIOR, MADHYA PRADESH",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-05 19:00:00",
            "status": "PKD",
            "activity": "Picked from shipper",
            "location": "DELHI, DELHI",
            "sr-status": "6",
            "sr-status-label": "SHIPPED",
        },
    ],
)

AWB_PUN_004 = _base_tracking(
    awb_code="AWB-PUN-004",
    origin="Pune",
    destination="Bangalore",
    courier_name="Ecom Express",
    pickup_date="2022-07-15 09:00:00",
    delivered_date="2022-07-16 18:00:00",
    current_status="Delivered",
    etd="2022-07-17 23:59:00",
    activities=[
        {
            "date": "2022-07-16 18:00:00",
            "status": "DLVD",
            "activity": "Delivered",
            "location": "BANGALORE, KARNATAKA",
            "sr-status": "7",
            "sr-status-label": "DELIVERED",
        },
        {
            "date": "2022-07-16 09:30:00",
            "status": "OFD",
            "activity": "Out for Delivery",
            "location": "BANGALORE, KARNATAKA",
            "sr-status": "17",
            "sr-status-label": "OUT FOR DELIVERY",
        },
        {
            "date": "2022-07-15 22:00:00",
            "status": "IT",
            "activity": "InTransit from Pune",
            "location": "HUBLI, KARNATAKA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-15 11:00:00",
            "status": "PKD",
            "activity": "Picked from shipper",
            "location": "PUNE, MAHARASHTRA",
            "sr-status": "6",
            "sr-status-label": "SHIPPED",
        },
    ],
)

AWB_KOL_005 = _base_tracking(
    awb_code="AWB-KOL-005",
    origin="Kolkata",
    destination="Bangalore",
    courier_name="Gati",
    pickup_date="2022-07-01 09:00:00",
    delivered_date=None,
    current_status="In Transit",
    etd="2022-07-08 23:59:00",
    activities=[
        {
            "date": "2022-07-10 10:00:00",
            "status": "IT",
            "activity": "InTransit - departed Hyderabad hub (late)",
            "location": "HYDERABAD, TELANGANA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-06 09:00:00",
            "status": "IT",
            "activity": "InTransit - arrived at Hyderabad hub",
            "location": "HYDERABAD, TELANGANA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-03 12:00:00",
            "status": "IT",
            "activity": "InTransit from Kolkata",
            "location": "BHUBANESWAR, ODISHA",
            "sr-status": "18",
            "sr-status-label": "IN TRANSIT",
        },
        {
            "date": "2022-07-01 18:00:00",
            "status": "PKD",
            "activity": "Picked from shipper",
            "location": "KOLKATA, WEST BENGAL",
            "sr-status": "6",
            "sr-status-label": "SHIPPED",
        },
    ],
)

_MOCK_TRACKING: dict[str, dict[str, Any]] = {
    "AWB-CHEN-001": AWB_CHEN_001,
    "AWB-MUM-002": AWB_MUM_002,
    "AWB-DEL-003": AWB_DEL_003,
    "AWB-PUN-004": AWB_PUN_004,
    "AWB-KOL-005": AWB_KOL_005,
}


def get_tracking(awb_code: str) -> dict[str, Any] | None:
    """Return mock tracking payload for a given AWB code, or None if unknown."""
    return _MOCK_TRACKING.get(awb_code)
