"""Shared constants and utilities for shipment risk analysis.

Both ``app.services.shipping_agent`` (home-screen flow) and
``app.agents.shipment`` (dashboard LangGraph flow) import from here so
that editing the system prompt or fallback values in one place takes
effect in both flows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# System prompt (single source of truth for both flows)
# ---------------------------------------------------------------------------

SHIPMENT_RISK_SYSTEM_PROMPT = (
    "You are a Shipment Risk Intelligence Agent for a global manufacturing supply chain.\n\n"
    "You will receive a structured narrative with three sections:\n"
    "  1. OEM (buyer) — location, country, commodities sourced.\n"
    "  2. Supplier — name, city, country, commodities supplied.\n"
    "  3. Shipment route plan — a leg-by-leg breakdown of the journey with:\n"
    "       - Leg type: ROAD, SEA, or PORT_DWELL\n"
    "       - Leg name and location\n"
    "       - Planned arrival, actual arrival, and departure time (if available)\n"
    "       - Port dwell time (hours a shipment has been sitting at a port without departing)\n"
    "       - Whether the leg is COMPLETED, IN_PROGRESS, or PENDING\n"
    "       - Current checkpoint sequence vs. total legs\n"
    "       - Overall planned vs. actual transit days\n\n"
    "DETECTION RULES — apply ALL of the following:\n\n"
    "RULE 1 — DELAY RISK (checkpoint lateness):\n"
    "  A leg is delayed when actual_arrival is later than planned_arrival.\n"
    "  Score: 1 day late → 15 pts; 2 days → 25 pts; 3 days → 40 pts; 4–5 days → 60 pts;\n"
    "  6–7 days → 75 pts; >7 days → 90+ pts. Cap at 100.\n"
    "  Use the worst single-leg delay as the delay_risk score.\n"
    "  Example: Sea departure New York, planned Mumbai arrival Feb 20, actual Feb 25 → 5-day\n"
    "  delay → delay_risk ~60; flag 'Sea leg arrived 5 days late at Mumbai'.\n\n"
    "RULE 2 — STAGNATION RISK (shipment stuck at a location):\n"
    "  Triggered when a shipment has arrived at a checkpoint but has NO departure_time\n"
    "  and the next leg is still PENDING.\n"
    "  Compute dwell = today's date − actual_arrival of the stagnant leg.\n"
    "  Score: dwell 1–3 days → 20 pts; 4–7 days → 45 pts; 8–14 days → 70 pts; >14 days → 90 pts.\n"
    "  This applies equally to port dwell (ship arrived, sea leg not yet departed) and\n"
    "  inland hubs (road leg arrived, next road leg not started).\n"
    "  Example: Arrived Port Klang Feb 24, no departure, today Feb 28 → 4-day dwell\n"
    "  → stagnation_risk ~45; flag 'Shipment stagnant at Port Klang for 4 days — sea leg not started'.\n\n"
    "RULE 3 — VELOCITY RISK (pace slower than planned):\n"
    "  Compare actual transit days to planned transit days at each leg.\n"
    "  velocity_deviation = (actual − planned) / planned × 100 %.\n"
    "  Score: 0–20% slower → 15 pts; 21–40% → 35 pts; 41–60% → 55 pts;\n"
    "  61–80% → 70 pts; >80% slower → 85 pts.\n"
    "  Also flag when a SEA leg shows significant transit overrun — indicates vessel speed\n"
    "  issues or route deviation.\n"
    "  Example: Shanghai→Kolkata planned 18 days, actual 26 days → 44% overrun\n"
    "  → velocity_risk ~55; flag 'Sea leg velocity dropped — 44% slower than planned'.\n\n"
    "RULE 4 — PENDING DOWNSTREAM LEGS:\n"
    "  If one or more legs AFTER the current position are still PENDING and the shipment\n"
    "  is already delayed or stagnant, amplify the overall score.\n"
    "  State each pending leg explicitly in risk_factors.\n"
    "  Example: Shipment at Mumbai port, final road leg to OEM plant not started\n"
    "  → flag 'Final road delivery leg pending — last-mile risk elevated'.\n\n"
    "RULE 5 — REGIONAL / ROUTE RISK:\n"
    "  Consider the ports and countries in the route plan. Flag known risk corridors:\n"
    "  - Sea routes through Indian Ocean / Bay of Bengal during Jun–Sep (monsoon/cyclone season)\n"
    "  - Trans-Pacific and Trans-Atlantic routes with known congestion\n"
    "  - Cross-border legs involving customs-heavy corridors\n"
    "  Add this as a risk_factor if relevant to the current route and today's date.\n\n"
    "Scoring guidelines (0–100 per risk dimension):\n"
    "  0–25  → low      (within normal tolerance)\n"
    "  26–50 → medium   (monitor closely)\n"
    "  51–75 → high     (escalate; notify logistics team)\n"
    "  76–100 → critical (immediate intervention required)\n\n"
    "Overall shipping_risk_score (0.0–1.0) = max(delay_score, stagnation_score, velocity_score) / 100.\n"
    "risk_level maps as: ≤0.25 → Low, ≤0.50 → Medium, ≤0.75 → High, >0.75 → Critical.\n\n"
    "risk_factors: List each flagged issue as a specific, data-grounded sentence.\n"
    "recommended_actions: One concrete action per risk factor (contact carrier, expedite customs, etc.).\n\n"
    "Return a single JSON object with EXACTLY this shape — no prose outside the JSON:\n"
    "{{\n"
    '  "shipping_risk_score": <float 0.0-1.0>,\n'
    '  "risk_level": <"Low" | "Medium" | "High" | "Critical">,\n'
    '  "delay_risk": {{ "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> }},\n'
    '  "stagnation_risk": {{ "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> }},\n'
    '  "velocity_risk": {{ "score": <0-100>, "label": <"low"|"medium"|"high"|"critical"> }},\n'
    '  "risk_factors": [<string>, ...],\n'
    '  "recommended_actions": [<string>, ...],\n'
    '  "shipment_metadata": {{ <summary of key fields> }}\n'
    "}}\n"
)

# ---------------------------------------------------------------------------
# Fallback result (used when LLM is unavailable or errors)
# ---------------------------------------------------------------------------

SHIPMENT_FALLBACK_RESULT: dict[str, Any] = {
    "shipping_risk_score": 0.5,
    "risk_level": "Medium",
    "delay_risk": {"score": 50, "label": "medium"},
    "stagnation_risk": {"score": 50, "label": "medium"},
    "velocity_risk": {"score": 0, "label": "low"},
    "risk_factors": ["Agent unavailable; risk could not be assessed"],
    "recommended_actions": ["Manually review shipments for this supplier"],
    "shipment_metadata": None,
}

# ---------------------------------------------------------------------------
# Shared tracking parse utilities
# ---------------------------------------------------------------------------


def _parse_datetime(raw: str | None) -> datetime | None:
    """Best-effort parse of a datetime string."""
    if not raw:
        return None
    cleaned = raw.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _max_checkpoint_gap_days(checkpoints: list[dict[str, Any]]) -> int:
    """Compute the largest gap (in days) between consecutive checkpoint arrivals."""
    dates: list[datetime] = []
    for cp in checkpoints:
        dt = _parse_datetime(cp.get("actual_arrival"))
        if dt:
            dates.append(dt)
    if len(dates) < 2:
        return 0
    dates.sort()
    max_gap = 0
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap > max_gap:
            max_gap = gap
    return max_gap


def parse_tracking_data_to_records(
    tracking_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse raw Shiprocket-format tracking_data into structured records.

    Expects ``tracking_data`` with ``route_plan`` (list of checkpoint dicts)
    and ``shipment_meta`` (origin, destination, etd, pickup_date, etc.).
    Computes per-shipment metrics: delayDays, daysWithoutMovement,
    plannedTransitDays, actualTransitDays.

    Returns a list of record dicts (0 or 1 entry based on available data).
    """
    route_plan = tracking_data.get("route_plan") or []
    shipment_meta = tracking_data.get("shipment_meta") or {}

    if not shipment_meta and not route_plan:
        return []

    origin_info = shipment_meta.get("origin") or {}
    dest_info = shipment_meta.get("destination") or {}
    origin = origin_info.get("city") or ""
    destination = dest_info.get("city") or ""
    route = f"{origin} → {destination}" if origin and destination else "unknown"
    current_status = shipment_meta.get("current_status") or "unknown"

    pickup_date_dt = _parse_datetime(shipment_meta.get("pickup_date"))
    etd_dt = _parse_datetime(shipment_meta.get("etd"))

    sorted_checkpoints = sorted(
        (cp for cp in route_plan if isinstance(cp, dict)),
        key=lambda cp: cp.get("sequence", 0),
    )

    # Last actual arrival across all checkpoints
    last_actual_dt: datetime | None = None
    for cp in sorted_checkpoints:
        dt = _parse_datetime(cp.get("actual_arrival"))
        if dt and (last_actual_dt is None or dt > last_actual_dt):
            last_actual_dt = dt

    # Planned transit days
    planned_transit_days = shipment_meta.get("transit_days_estimated") or 0
    if not planned_transit_days and pickup_date_dt and etd_dt:
        planned_transit_days = max(1, (etd_dt - pickup_date_dt).days)

    # Actual transit days
    actual_transit_days = planned_transit_days
    if pickup_date_dt and last_actual_dt:
        actual_transit_days = max(1, (last_actual_dt - pickup_date_dt).days)

    # Delay: max days a checkpoint arrived past its planned_arrival
    delay_days = 0
    for cp in sorted_checkpoints:
        planned = _parse_datetime(cp.get("planned_arrival"))
        actual = _parse_datetime(cp.get("actual_arrival"))
        if planned and actual and actual > planned:
            d = (actual - planned).days
            if d > delay_days:
                delay_days = d

    # Stagnation: max gap between consecutive checkpoint arrivals
    days_without_movement = _max_checkpoint_gap_days(sorted_checkpoints)

    # Live port/hub dwell: if the last checkpoint has an actual_arrival but no
    # departure_time, the shipment may be stagnant right now.  Compute dwell
    # against today so stagnation_risk reflects real-time exposure.
    port_dwell_days = 0
    if sorted_checkpoints:
        last_cp = sorted_checkpoints[-1]
        last_arrival_dt = _parse_datetime(last_cp.get("actual_arrival"))
        has_departure = bool(last_cp.get("departure_time"))
        if last_arrival_dt and not has_departure:
            today = datetime.now(timezone.utc).replace(tzinfo=None)
            dwell = (today - last_arrival_dt).days
            if dwell > 0:
                port_dwell_days = dwell
                if dwell > days_without_movement:
                    days_without_movement = dwell

    return [
        {
            "route": route,
            "origin": origin,
            "destination": destination,
            "status": current_status,
            "delayDays": delay_days,
            "daysWithoutMovement": days_without_movement,
            "portDwellDays": port_dwell_days,
            "plannedTransitDays": planned_transit_days,
            "actualTransitDays": actual_transit_days,
            "checkpoints": sorted_checkpoints,
        }
    ]


def extract_tracking_data_from_records(
    raw_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract the tracking_data dict from a list of mock-server records.

    The mock server returns a list of items; the first record's
    ``tracking_data`` key (Shiprocket format) is used.
    """
    if not raw_records:
        return {}
    first = raw_records[0]
    if not isinstance(first, dict):
        return {}
    return first.get("tracking_data") or first


def _leg_status(cp: dict[str, Any]) -> str:
    """Derive a human-readable leg status from checkpoint fields."""
    actual_arr = cp.get("actual_arrival")
    departure = cp.get("departure_time")
    if actual_arr and departure:
        return "COMPLETED"
    if actual_arr and not departure:
        return "IN_PROGRESS (arrived, not yet departed)"
    return "PENDING"


def build_narrative_context(
    oem: dict[str, Any],
    supplier: dict[str, Any],
    tracking_records: list[dict[str, Any]],
) -> str:
    """Build a plain-English narrative from OEM, supplier, and tracking data.

    Sent to the LLM as the user message so it can reason about leg-by-leg
    route progress, port dwell, velocity, and pending downstream legs.
    """
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    lines: list[str] = []

    lines.append(f"Today's date: {today.strftime('%Y-%m-%d')}")
    lines.append("")

    # --- OEM section ---
    oem_name = oem.get("name") or "Unknown OEM"
    oem_locations = oem.get("locations") or []
    oem_location_str = (
        ", ".join(
            (l.get("city") or l.get("name") or str(l)) if isinstance(l, dict) else str(l)
            for l in oem_locations
        ) if oem_locations else "unknown location"
    )
    oem_commodities = oem.get("commodities") or []
    oem_commodity_str = ", ".join(str(c) for c in oem_commodities) if oem_commodities else "unspecified commodities"

    lines.append("=== OEM (Buyer) Details ===")
    lines.append(f"Name: {oem_name}")
    lines.append(f"Location(s): {oem_location_str}")
    lines.append(f"Commodities sourced: {oem_commodity_str}")
    lines.append("")

    # --- Supplier section ---
    supplier_name = supplier.get("name") or "Unknown Supplier"
    supplier_city = supplier.get("city") or ""
    supplier_country = supplier.get("country") or ""
    supplier_location = supplier.get("location") or ""
    supplier_loc_str = (
        ", ".join(filter(None, [supplier_city, supplier_country, supplier_location]))
        or "unknown location"
    )
    supplier_commodities = supplier.get("commodities") or []
    supplier_commodity_str = (
        ", ".join(str(c) for c in supplier_commodities) if supplier_commodities else "unspecified"
    )

    lines.append("=== Supplier Details ===")
    lines.append(f"Name: {supplier_name}")
    lines.append(f"Location: {supplier_loc_str}")
    lines.append(f"Commodities supplied: {supplier_commodity_str}")
    lines.append("")

    # --- Tracking section ---
    lines.append("=== Shipment Route Plan ===")
    if not tracking_records:
        lines.append("No tracking data is available for this supplier.")
    else:
        for idx, record in enumerate(tracking_records, start=1):
            route = record.get("route") or "unknown route"
            origin = record.get("origin") or "unknown"
            destination = record.get("destination") or "unknown"
            status = record.get("status") or "unknown"
            delay_days = int(record.get("delayDays") or 0)
            stagnation_days = int(record.get("daysWithoutMovement") or 0)
            port_dwell_days = int(record.get("portDwellDays") or 0)
            planned_transit = int(record.get("plannedTransitDays") or 0)
            actual_transit = int(record.get("actualTransitDays") or planned_transit)
            checkpoints: list[dict[str, Any]] = record.get("checkpoints") or []
            total_legs = len(checkpoints)
            current_seq = max((cp.get("sequence", 0) for cp in checkpoints), default=0)

            lines.append(f"Shipment {idx}: {route}")
            lines.append(f"  Origin: {origin}  |  Final destination: {destination}")
            lines.append(f"  Overall status: {status}")
            lines.append(
                f"  Transit plan: estimated {planned_transit} day(s); "
                f"elapsed so far: {actual_transit} day(s)"
            )
            if planned_transit > 0:
                pct = round((actual_transit / planned_transit - 1.0) * 100)
                if pct > 0:
                    lines.append(f"  Overall transit overrun: {pct}% longer than planned")
                elif pct < 0:
                    lines.append(f"  Overall transit underrun: {abs(pct)}% faster than planned")
                else:
                    lines.append("  Overall transit: exactly on schedule")
            lines.append(f"  Progress: leg {current_seq} of {total_legs} total legs")
            lines.append("")

            # Per-leg breakdown
            lines.append(f"  Leg-by-leg breakdown:")
            for cp in checkpoints:
                seq = cp.get("sequence", "?")
                leg_type = (cp.get("leg_type") or cp.get("mode") or "UNKNOWN").upper()
                raw_name = cp.get("checkpoint_name") or cp.get("location")
                if isinstance(raw_name, dict):
                    raw_name = raw_name.get("city") or raw_name.get("name") or str(raw_name)
                cp_name = str(raw_name) if raw_name else f"Leg {seq}"
                planned_arr_str = cp.get("planned_arrival") or "—"
                actual_arr_str = cp.get("actual_arrival") or "—"
                departure_str = cp.get("departure_time") or None
                leg_st = _leg_status(cp)

                lines.append(f"    Leg {seq} [{leg_type}] — {cp_name}")
                lines.append(f"      Status: {leg_st}")
                lines.append(f"      Planned arrival : {planned_arr_str}")
                lines.append(f"      Actual arrival  : {actual_arr_str}")

                # Departure / dwell
                if departure_str:
                    lines.append(f"      Departure       : {departure_str}")
                else:
                    actual_arr_dt = _parse_datetime(actual_arr_str)
                    if actual_arr_dt:
                        dwell = (today - actual_arr_dt).days
                        lines.append(
                            f"      Departure       : NOT YET DEPARTED "
                            f"(dwell so far: {dwell} day(s))"
                        )
                    else:
                        lines.append("      Departure       : not yet departed")

                # Per-leg delay
                planned_arr_dt = _parse_datetime(cp.get("planned_arrival"))
                actual_arr_dt2 = _parse_datetime(cp.get("actual_arrival"))
                if planned_arr_dt and actual_arr_dt2:
                    d = (actual_arr_dt2 - planned_arr_dt).days
                    if d > 0:
                        lines.append(f"      Arrival delay   : {d} day(s) late vs plan")
                    else:
                        lines.append("      Arrival delay   : on time or early")
                lines.append("")

            # Summary signals
            if delay_days > 0:
                lines.append(f"  ⚠ Maximum single-leg arrival delay: {delay_days} day(s)")
            if port_dwell_days > 0:
                lines.append(
                    f"  ⚠ Current port/hub dwell (no departure): {port_dwell_days} day(s) "
                    f"as of today ({today.strftime('%Y-%m-%d')})"
                )
            elif stagnation_days > 0:
                lines.append(
                    f"  ⚠ Longest gap without movement between legs: {stagnation_days} day(s)"
                )

            # Pending downstream legs
            pending_legs = [
                cp for cp in checkpoints if _leg_status(cp) == "PENDING"
            ]
            if pending_legs:
                pending_names = []
                for cp in pending_legs:
                    raw = cp.get("checkpoint_name") or cp.get("location")
                    if isinstance(raw, dict):
                        raw = raw.get("city") or raw.get("name") or str(raw)
                    pending_names.append(str(raw) if raw else f"Leg {cp.get('sequence', '?')}")
                lines.append(
                    f"  Pending downstream legs ({len(pending_legs)}): "
                    + ", ".join(pending_names)
                )
            lines.append("")

    lines.append(
        "Apply RULES 1–5 from your instructions to the data above. "
        "Flag every detected risk with specific leg names, dates, and day counts. "
        "Return ONLY the JSON risk assessment."
    )

    return "\n".join(lines)
