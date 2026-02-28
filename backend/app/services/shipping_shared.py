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
 ''' 
You are a Shipment Risk Intelligence Agent for a global manufacturing supply chain.

You will receive a structured shipment narrative that includes:

Today's date (authoritative reference date for all timing calculations)

OEM (buyer) details

Supplier details

Shipment route plan

Leg-by-leg shipment breakdown including:

transport_mode

status (COMPLETED | CURRENT | UPCOMING)

planned_arrival (ISO timestamp)

actual_arrival (ISO timestamp or null)

departure_time (ISO timestamp or null)

timing_note (explicit instruction about delay interpretation)

dwell_days (if provided for current leg)

current_checkpoint_sequence

overall status

current location

total legs

CRITICAL INTERPRETATION RULES:

The provided “Today's date” is the only valid reference date.

If timing_note says:

"NOT YET DUE — do NOT treat as delayed"
→ You MUST NOT classify that leg as delayed.

If actual_arrival equals planned_arrival
→ Treat as ON TIME.

If departure_time is null AND status is CURRENT
→ Evaluate stagnation risk using dwell_days (if provided).

Do NOT assume delay unless there is explicit deviation between planned and actual timestamps.

Do NOT fabricate missing timestamps.

UPCOMING legs with future planned_arrival dates are NOT delayed.

Your Responsibilities:

Analyze shipment progression logically across legs.

Evaluate three independent risk dimensions:

A) Delay Risk

Based strictly on planned vs actual deviation.

Ignore UPCOMING legs marked NOT YET DUE.

B) Stagnation Risk

Based on dwell_days at CURRENT leg.

Consider 0–2 days normal.

3–5 days moderate concern.

5 days elevated concern.

C) Velocity Risk

Based on abnormal lag between arrival and departure.

Consider excessive port dwell or lack of movement.

Assign 0–100 score for each risk category using proportional reasoning.

Compute shipping_risk_score as a normalized float between 0.0–1.0.

It should reflect weighted severity of the three categories.

Assign risk_level:

Low

Medium

High

Critical
Escalate if multiple categories exceed medium.

Identify ONLY data-supported risk_factors.

Each factor must reference concrete evidence from the narrative.

Example: "Shipment dwelling 4 days at Port Klang without departure."

Provide operationally specific recommended_actions.

Must be leg-specific.

Must align with transport_mode.

Must be actionable (expedite clearance, reroute, switch to air, trigger supplier escalation, etc.)

Avoid generic advice.

Output Requirements:

Return EXACTLY one JSON object.
No explanation.
No markdown.
No commentary.
No extra keys.
No text outside JSON.

{{
"shipping_risk_score": <float 0.0-1.0>,
"risk_level": "Low" | "Medium" | "High" | "Critical",
"delay_risk": {{ "score": <0-100>, "label": "low"|"medium"|"high"|"critical" }},
"stagnation_risk": {{ "score": <0-100>, "label": "low"|"medium"|"high"|"critical" }},
"velocity_risk": {{ "score": <0-100>, "label": "low"|"medium"|"high"|"critical" }},
"risk_factors": [
"<clear, data-supported factor>"
],
"recommended_actions": [
"<specific operational mitigation>"
],
"shipment_metadata": {{
"origin": "<city>",
"destination": "<city>",
"current_location": "<city>",
"current_status": "<status>",
"current_checkpoint_sequence": <integer>,
"total_legs": <integer>,
"current_leg_transport_mode": "<mode>"
}}
}}

Hard Constraints:

Never contradict timing_note.

Never treat UPCOMING future legs as delayed.

Never infer weather, geopolitical, or port congestion risk unless explicitly present.

If all legs are on time and dwell is within normal threshold, return low scores with justification.

Output must be valid JSON parsable by a strict JSON parser.
 '''
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
    route = f"{origin} → {destination}" if origin and destination else "—"
    current_status = shipment_meta.get("current_status") or "—"

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
    """Derive a human-readable leg status from checkpoint fields.

    Uses the terminology the system prompt expects:
      COMPLETED — arrived and departed
      CURRENT   — arrived but not yet departed
      UPCOMING  — not yet arrived
    """
    actual_arr = cp.get("actual_arrival")
    departure = cp.get("departure_time")
    if actual_arr and departure:
        return "COMPLETED"
    if actual_arr and not departure:
        return "CURRENT"
    return "UPCOMING"


def _commodities_to_str(commodities: Any) -> str:
    """Format commodities for narrative: accept list of items or a single string."""
    if commodities is None:
        return "unspecified"
    if isinstance(commodities, str):
        return commodities.strip() or "unspecified"
    if isinstance(commodities, (list, tuple)):
        return ", ".join(str(c) for c in commodities) if commodities else "unspecified"
    return str(commodities)


def build_narrative_context(
    oem: dict[str, Any],
    supplier: dict[str, Any],
    tracking_records: list[dict[str, Any]],
) -> str:
    """Build a structured shipment narrative aligned with the system prompt.

    The narrative presents data in the format the LLM expects:
      1) Today's date
      2) OEM (buyer) — location, commodities
      3) Supplier — name, city, country, commodities
      4) Shipment route plan — leg-by-leg with transport_mode, location,
         planned_arrival, actual_arrival, departure_time, status, sequence,
         current_checkpoint_sequence, overall planned vs actual transit days
    """
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    lines: list[str] = []

    lines.append(f"Today's date: {today.strftime('%Y-%m-%d')}")
    lines.append("")

    # --- OEM section ---
    oem_name = oem.get("name") or "—"
    oem_locations = oem.get("locations") or []
    oem_location_str = (
        ", ".join(
            (l.get("city") or l.get("name") or str(l)) if isinstance(l, dict) else str(l)
            for l in oem_locations
        ) if oem_locations else "—"
    )
    oem_commodities = oem.get("commodities") or []
    oem_commodity_str = _commodities_to_str(oem_commodities)

    lines.append("=== OEM (Buyer) ===")
    lines.append(f"Name: {oem_name}")
    lines.append(f"Location: {oem_location_str}")
    lines.append(f"Commodities sourced: {oem_commodity_str}")
    lines.append("")

    # --- Supplier section ---
    supplier_name = supplier.get("name") or "—"
    supplier_city = supplier.get("city") or ""
    supplier_country = supplier.get("country") or ""
    supplier_location = supplier.get("location") or ""
    supplier_loc_str = (
        ", ".join(filter(None, [supplier_city, supplier_country, supplier_location]))
        or "—"
    )
    supplier_commodities = supplier.get("commodities") or []
    supplier_commodity_str = _commodities_to_str(supplier_commodities)

    lines.append("=== Supplier ===")
    lines.append(f"Name: {supplier_name}")
    lines.append(f"Location: {supplier_loc_str}")
    lines.append(f"Commodities supplied: {supplier_commodity_str}")
    lines.append("")

    # --- Shipment route plan ---
    lines.append("=== Shipment Route Plan ===")
    if not tracking_records:
        lines.append("No tracking data is available for this supplier.")
    else:
        for idx, record in enumerate(tracking_records, start=1):
            route = record.get("route") or "—"
            origin = record.get("origin") or "—"
            destination = record.get("destination") or "—"
            status = record.get("status") or "—"
            checkpoints: list[dict[str, Any]] = record.get("checkpoints") or []
            total_legs = len(checkpoints)

            # current_checkpoint_sequence: highest sequence with an actual_arrival
            current_checkpoint_seq = 0
            current_location = "—"
            current_transport_mode = "—"
            for cp in checkpoints:
                if cp.get("actual_arrival"):
                    seq = cp.get("sequence", 0)
                    if seq >= current_checkpoint_seq:
                        current_checkpoint_seq = seq
                        raw_loc = cp.get("checkpoint_name") or cp.get("location")
                        if isinstance(raw_loc, dict):
                            raw_loc = raw_loc.get("city") or raw_loc.get("name") or str(raw_loc)
                        current_location = str(raw_loc) if raw_loc else f"Leg {seq}"
                        current_transport_mode = (
                            cp.get("transport_mode") or cp.get("leg_type") or cp.get("mode") or "—"
                        ).strip().upper()
                        if current_transport_mode == "—":
                            current_transport_mode = "—"

            lines.append(f"Shipment {idx}: {route}")
            lines.append(f"  Origin: {origin}")
            lines.append(f"  Destination: {destination}")
            lines.append(f"  Overall status: {status}")
            lines.append(f"  Total legs: {total_legs}")
            lines.append(f"  Current checkpoint sequence: {current_checkpoint_seq}")
            lines.append(f"  Current location: {current_location}")
            if current_transport_mode and current_transport_mode != "—":
                lines.append(f"  Current leg transport mode: {current_transport_mode}")
            lines.append("")

            # Leg-by-leg breakdown
            lines.append("  Leg-by-leg breakdown:")
            for cp in checkpoints:
                seq = cp.get("sequence", "?")
                transport_mode = (cp.get("transport_mode") or cp.get("leg_type") or cp.get("mode") or "—").strip().upper()
                if transport_mode == "—":
                    transport_mode = "—"

                raw_name = cp.get("checkpoint_name") or cp.get("location")
                if isinstance(raw_name, dict):
                    raw_name = raw_name.get("city") or raw_name.get("name") or str(raw_name)
                cp_name = str(raw_name) if raw_name else f"Leg {seq}"

                planned_arr = cp.get("planned_arrival") or None
                actual_arr = cp.get("actual_arrival") or None
                departure = cp.get("departure_time") or None
                leg_st = _leg_status(cp)

                lines.append(f"    Leg {seq}: {cp_name}")
                lines.append(f"      transport_mode: {transport_mode}")
                lines.append(f"      status: {leg_st}")
                lines.append(f"      planned_arrival: {planned_arr or 'null'}")
                lines.append(f"      actual_arrival: {actual_arr or 'null'}")
                lines.append(f"      departure_time: {departure or 'null'}")

                # Explicit per-leg timing assessment to prevent LLM hallucination
                if leg_st == "UPCOMING":
                    planned_arr_dt = _parse_datetime(planned_arr)
                    if planned_arr_dt:
                        days_until = (planned_arr_dt - today).days
                        if days_until >= 0:
                            lines.append(f"      timing_note: NOT YET DUE — planned arrival is {days_until} day(s) from today; do NOT treat as delayed")
                        else:
                            lines.append(f"      timing_note: OVERDUE — planned arrival was {abs(days_until)} day(s) ago but shipment has not arrived yet")
                    else:
                        lines.append("      timing_note: UPCOMING — no actual arrival yet")
                elif leg_st == "COMPLETED" or leg_st == "CURRENT":
                    planned_arr_dt = _parse_datetime(planned_arr)
                    actual_arr_dt = _parse_datetime(actual_arr)
                    if planned_arr_dt and actual_arr_dt:
                        delta_days = (actual_arr_dt - planned_arr_dt).days
                        if delta_days > 0:
                            lines.append(f"      timing_note: LATE by {delta_days} day(s)")
                        elif delta_days < 0:
                            lines.append(f"      timing_note: EARLY by {abs(delta_days)} day(s)")
                        else:
                            lines.append("      timing_note: ON TIME")
                    elif actual_arr_dt:
                        lines.append("      timing_note: Arrived (no planned date to compare)")

                # Dwell calculation for CURRENT legs (arrived, not departed)
                if leg_st == "CURRENT" and actual_arr:
                    actual_arr_dt = _parse_datetime(actual_arr)
                    if actual_arr_dt:
                        dwell = (today - actual_arr_dt).days
                        lines.append(f"      dwell_days: {dwell}")

                lines.append("")

    return "\n".join(lines)
