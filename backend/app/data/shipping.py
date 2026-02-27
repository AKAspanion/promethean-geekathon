import random
from datetime import datetime, timedelta

from app.data.base import BaseDataSource, DataSourceResult


class ShippingRoutesDataSource(BaseDataSource):
    def get_type(self) -> str:
        return "shipping"

    async def _on_initialize(self) -> None:
        pass

    async def is_available(self) -> bool:
        return True

    async def fetch_data(self, params: dict | None = None) -> list[DataSourceResult]:
        """
        Return rich mock shipping data including a basic shipment timeline.

        This is intentionally deterministic in structure (but random in values)
        so downstream agents (e.g. Shipment Agent) can compute delay, stagnation,
        and velocity style risks from a day-wise timeline.
        """
        routes = (params or {}).get("routes") or [
            {"origin": "Shanghai", "destination": "Los Angeles"},
            {"origin": "Rotterdam", "destination": "Singapore"},
            {"origin": "Singapore", "destination": "Tokyo"},
        ]

        disruption_reasons = [
            "port_congestion",
            "weather",
            "labor_strike",
            "canal_delay",
            "vessel_shortage",
        ]

        results: list[DataSourceResult] = []
        today = datetime.utcnow().date()

        for route in routes:
            origin = route["origin"]
            destination = route["destination"]

            has_disruption = random.random() > 0.5
            reason = random.choice(disruption_reasons) if has_disruption else None
            delay_days = random.randint(1, 14) if has_disruption else 0

            planned_transit_days = random.randint(7, 18)
            actual_transit_days = planned_transit_days + delay_days

            timeline: list[dict] = []
            last_movement_day = 0

            for day in range(1, actual_transit_days + 1):
                date = today + timedelta(days=day - 1)

                if day == 1:
                    milestone = "depart_origin"
                    estimated_location = origin
                elif day == planned_transit_days:
                    milestone = "planned_arrival_destination"
                    estimated_location = destination
                elif day == actual_transit_days:
                    milestone = "actual_arrival_destination"
                    estimated_location = destination
                else:
                    milestone = "in_transit"
                    estimated_location = "at_sea"

                # Simple stagnation model: towards the end of the route we may see
                # multiple consecutive days without movement when disrupted.
                if (
                    has_disruption
                    and day > planned_transit_days - 2
                    and random.random() < 0.6
                ):
                    status = "no_movement"
                else:
                    status = "moved"
                    last_movement_day = day

                timeline.append(
                    {
                        "day": day,
                        "date": date.isoformat(),
                        "estimated_location": estimated_location,
                        "milestone": milestone,
                        "status": status,  # "moved" | "no_movement"
                    }
                )

            if last_movement_day:
                days_without_movement = actual_transit_days - last_movement_day
            else:
                days_without_movement = actual_transit_days

            payload = {
                "origin": origin,
                "destination": destination,
                "route": f"{origin} → {destination}",
                "status": "disrupted" if has_disruption else "normal",
                "delayDays": delay_days,
                "disruptionReason": reason,
                "vesselAvailability": "low" if has_disruption else "normal",
                "portConditions": "congested" if has_disruption else "normal",
                "estimatedRecoveryDays": (
                    delay_days + random.randint(0, 7) if has_disruption else 0
                ),
                "plannedTransitDays": planned_transit_days,
                "actualTransitDays": actual_transit_days,
                "daysWithoutMovement": days_without_movement,
                "timeline": timeline,
            }

            results.append(self._create_result(payload))

        return results
