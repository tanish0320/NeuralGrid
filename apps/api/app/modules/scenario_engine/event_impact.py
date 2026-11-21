from __future__ import annotations

from apps.api.app.core.database import utc_now
from apps.api.app.modules.dependency_graph.graph_builder import haversine_km
from apps.api.app.schemas.events import (
    AffectedCellImpact,
    AttendanceScenario,
    EventImpactRequest,
    EventImpactResponse,
    EventRecord,
)
from apps.api.app.schemas.networks import CellRecord

SCENARIO_MULTIPLIERS: dict[AttendanceScenario, float] = {
    "LOW": 0.75,
    "EXPECTED": 1.0,
    "HIGH": 1.35,
}


class EventNotConfirmedError(Exception):
    """Raised when event-to-cell impact is requested before operator confirmation."""


class EventMissingCoordinatesError(Exception):
    """Raised when an event has no confirmed venue coordinates."""


def calculate_event_impact(
    *,
    event: EventRecord,
    cells: list[CellRecord],
    request: EventImpactRequest,
) -> EventImpactResponse:
    """Map an operator-confirmed event onto nearby synthetic cells via configurable radius heuristic."""
    if event.status != "CONFIRMED":
        raise EventNotConfirmedError(
            f"Event {event.event_id} has status '{event.status}'. "
            "Operator confirmation (POST /api/v1/events/{event_id}/confirm) is required before impact mapping."
        )
    if event.latitude is None or event.longitude is None:
        raise EventMissingCoordinatesError(
            f"Event {event.event_id} lacks confirmed venue latitude/longitude coordinates."
        )

    radius_km = request.influence_radius_km
    if request.attendance_scenario == "LOW":
        effective_attendance = float(event.attendance_low or 12000)
    elif request.attendance_scenario == "HIGH":
        effective_attendance = float(event.attendance_high or 25000)
    else:
        if event.attendance_low is not None and event.attendance_high is not None:
            effective_attendance = (event.attendance_low + event.attendance_high) / 2.0
        elif event.attendance_high is not None:
            effective_attendance = float(event.attendance_high)
        elif event.attendance_low is not None:
            effective_attendance = float(event.attendance_low)
        else:
            effective_attendance = 15000.0

    # Synthetic demand scaling heuristic (never real RF coverage or real subscriber count)
    scenario_mult = SCENARIO_MULTIPLIERS[request.attendance_scenario]
    base_surge_mbps = (effective_attendance / 100.0) * 1.45 * event.intensity * scenario_mult

    affected: list[AffectedCellImpact] = []
    for cell in cells:
        if cell.initial_state == "STANDBY":
            continue
        dist_km = haversine_km(event.latitude, event.longitude, cell.lat, cell.lon)
        if dist_km <= radius_km:
            weight = round(max(0.08, 1.0 - (dist_km / radius_km) ** 1.35), 4)
            uplift = round(base_surge_mbps * weight, 2)
            affected.append(
                AffectedCellImpact(
                    cell_id=cell.cell_id,
                    distance_km=round(dist_km, 3),
                    impact_weight=weight,
                    estimated_additional_demand_mbps=uplift,
                    reason=(
                        f"Synthetic proximity weight {weight:.2f} at {dist_km:.2f} km "
                        f"within {radius_km:.1f} km radius (event_origin={event.event_origin})"
                    ),
                )
            )

    affected.sort(key=lambda item: (item.distance_km, item.cell_id))
    total_uplift = round(sum(item.estimated_additional_demand_mbps for item in affected), 2)

    return EventImpactResponse(
        event_id=event.event_id,
        simulation_id=request.simulation_id,
        influence_radius_km=radius_km,
        attendance_scenario=request.attendance_scenario,
        affected_cells=affected,
        total_estimated_uplift_mbps=total_uplift,
        assumptions={
            "proximity_model": "synthetic_haversine_heuristic_not_rf_propagation",
            "event_origin": event.event_origin,
            "verification_status": event.verification_status,
            "attendance_basis": event.attendance_basis,
            "effective_attendance_used": effective_attendance,
            "intensity_multiplier": event.intensity,
            "scenario_multiplier": scenario_mult,
            "disclaimer": "Synthetic event uplift model for simulation testing only; news mentions are not attendance.",
        },
        created_at=utc_now(),
    )
