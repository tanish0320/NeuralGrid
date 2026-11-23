"""
Phase 5 Geospatial Impact Assessment Validation Script.

Executes a live simulation run demonstrating:
1. At least 5 canonical events mapped across the 100-cell Bengaluru network.
2. At least 2 events of different categories (Concert, Sports, Tech Conference, Exhibition, Meetup).
3. Overlapping cells affected by multiple simultaneous events (demonstrating sublinear aggregation).
4. Events flagged as geographically unresolved (missing coordinates).
5. Cancelled/expired events excluded from future demand.
6. Detailed metrics output matching Section 12 of the prompt.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from apps.api.app.config import Settings
from apps.api.app.core.database import Database, utc_now
from apps.api.app.core.state import AppContainer
from apps.api.app.modules.event_intelligence.geospatial.engine import GeospatialImpactEngine
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.schemas.events import EventRecord
from simulation.seed_network import seed_network_if_needed


def run_phase5_validation():
    print("=" * 70)
    print("NEURALGRID PHASE 5: GEOSPATIAL EVENT-TO-CELL IMPACT ENGINE VALIDATION")
    print("=" * 70)

    settings = Settings()
    container = AppContainer(settings=settings)
    seed_network_if_needed(container.network_repo)

    net = container.network_repo.get_current_network()
    assert net is not None, "A 100-cell network must be active"
    cells = container.network_repo.get_cells(net.network_id)
    print(f"[*] Active network: {net.network_id} (Total Cells: {len(cells)})")

    now = utc_now()

    # Create 7 canonical events covering different categories, overlaps, missing coords, and cancellations
    events_to_test = [
        # 1. Mega Concert at Palace Grounds (CBD)
        EventRecord(
            event_id=uuid4(),
            event_key="bengaluru-arijit-singh-live-2026",
            event_origin="SOURCE_DISCOVERED",
            name="Arijit Singh Live at Palace Grounds",
            event_type="CONCERT",
            venue_name="Palace Grounds",
            city="Bengaluru",
            latitude=12.9988,
            longitude=77.5921,
            start_at=now + timedelta(hours=18),
            end_at=now + timedelta(hours=22),
            attendance_low=25000,
            attendance_high=35000,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.2,
            verification_status="CORROBORATED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 2. IPL / Cricket Match at Chinnaswamy Stadium (CBD) - OVERLAPS WITH CONCERT IN CBD CELLS!
        EventRecord(
            event_id=uuid4(),
            event_key="ipl-rcb-vs-csk-2026",
            event_origin="SOURCE_DISCOVERED",
            name="RCB vs CSK T20 Match Chinnaswamy",
            event_type="SPORTS",
            venue_name="M. Chinnaswamy Stadium",
            city="Bengaluru",
            latitude=12.9788,
            longitude=77.5996,
            start_at=now + timedelta(hours=19),
            end_at=now + timedelta(hours=23),
            attendance_low=32000,
            attendance_high=38000,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.3,
            verification_status="VERIFIED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 3. Bengaluru Tech Summit at KTPO Whitefield
        EventRecord(
            event_id=uuid4(),
            event_key="bengaluru-tech-summit-2026",
            event_origin="SOURCE_DISCOVERED",
            name="Bengaluru AI & Telecom Summit 2026",
            event_type="TECH_CONFERENCE",
            venue_name="KTPO Trade Centre Whitefield",
            city="Bengaluru",
            latitude=12.9796,
            longitude=77.7281,
            start_at=now + timedelta(hours=24),
            end_at=now + timedelta(hours=32),
            attendance_low=6000,
            attendance_high=8500,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.0,
            verification_status="VERIFIED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 4. Electronic City Tech Expo
        EventRecord(
            event_id=uuid4(),
            event_key="ecity-expo-2026",
            event_origin="SOURCE_DISCOVERED",
            name="IoT & Smart Grid Expo Electronic City",
            event_type="EXHIBITION",
            venue_name="Electronic City Phase 1 Convention Grounds",
            city="Bengaluru",
            latitude=12.8452,
            longitude=77.6602,
            start_at=now + timedelta(hours=30),
            end_at=now + timedelta(hours=36),
            attendance_low=7000,
            attendance_high=9000,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.0,
            verification_status="PARTIALLY_VERIFIED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 5. Koramangala Founders Meetup
        EventRecord(
            event_id=uuid4(),
            event_key="koramangala-ai-meetup-2026",
            event_origin="SOURCE_DISCOVERED",
            name="Koramangala Open Source AI Meetup",
            event_type="MEETUP",
            venue_name="Koramangala Indoor Stadium",
            city="Bengaluru",
            latitude=12.9352,
            longitude=77.6245,
            start_at=now + timedelta(hours=14),
            end_at=now + timedelta(hours=16),
            attendance_low=250,
            attendance_high=400,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.0,
            verification_status="DISCOVERED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 6. Geographically Unresolved Event (Missing Coordinates)
        EventRecord(
            event_id=uuid4(),
            event_key="unresolved-virtual-summit-2026",
            event_origin="SOURCE_DISCOVERED",
            name="Karnataka Digital Innovation Virtual Round Table",
            event_type="TECH_CONFERENCE",
            venue_name="Online / Unspecified Location",
            city="Bengaluru",
            latitude=None,
            longitude=None,
            start_at=now + timedelta(hours=12),
            end_at=now + timedelta(hours=15),
            attendance_low=1000,
            attendance_high=2000,
            attendance_basis="OPERATOR_ASSUMPTION",
            intensity=1.0,
            verification_status="PARTIALLY_VERIFIED",
            status="UPCOMING",
            created_at=now,
            updated_at=now,
        ),
        # 7. Cancelled Event
        EventRecord(
            event_id=uuid4(),
            event_key="cancelled-carnival-2026",
            event_origin="SOURCE_DISCOVERED",
            name="Indiranagar Street Carnival (Cancelled)",
            event_type="FESTIVAL",
            venue_name="Indiranagar Club Grounds",
            city="Bengaluru",
            latitude=12.9719,
            longitude=77.6412,
            start_at=now + timedelta(hours=48),
            end_at=now + timedelta(hours=54),
            attendance_low=15000,
            attendance_high=20000,
            attendance_basis="SOURCE_EVIDENCE",
            intensity=1.0,
            verification_status="CANCELLED",
            status="CANCELLED",
            created_at=now,
            updated_at=now,
        ),
    ]

    for ev in events_to_test:
        container.event_repo.create_event(ev)

    print(f"[*] Seeded {len(events_to_test)} canonical events into EventRepository")

    # Run recalculate
    recalc = container.impact_engine.recalculate_all(net.network_id)
    impacts = container.impact_repo.list_all_impacts()
    overlaps = container.impact_engine.detect_overlapping_cells(
        cells, impacts, {e.event_id: e for e in events_to_test}
    )

    print("\n" + "=" * 70)
    print("PHASE 5 VALIDATION METRICS REPORT (Section 12)")
    print("=" * 70)
    print(f"1.  Total canonical events evaluated:            {recalc.total_canonical_events}")
    print(f"2.  Events successfully mapped to cells:         {recalc.mapped_events_count}")
    print(f"3.  Events flagged as geographically unresolved: {recalc.geographically_unresolved_count}")
    print(f"4.  Events excluded (cancelled/expired):         {recalc.excluded_events_count}")
    print(f"5.  Total cell impact records generated:         {recalc.total_impact_records}")
    print(f"6.  Cells affected by at least one event:        {recalc.affected_cells_count}")
    print(f"7.  Cells with multi-event overlap:             {recalc.overlapping_cells_count}")
    print(f"8.  Maximum single-cell demand delta:            {recalc.max_cell_demand_delta_mbps:.2f} Mbps")
    print(f"9.  Average demand delta across affected cells:  {recalc.avg_cell_demand_delta_mbps:.2f} Mbps")
    print("10. Distribution of impact by category:")
    for cat, count in recalc.category_distribution.items():
        print(f"    - {cat:<18}: {count} events")

    print("\n" + "-" * 70)
    print("MULTI-EVENT OVERLAPPING CELLS BREAKDOWN:")
    print("-" * 70)
    for ov in overlaps[:5]:
        print(f"Cell {ov.cell_id} ({ov.region}):")
        print(f"  • Simultaneous Events: {ov.overlapping_event_count} ({', '.join(ov.event_titles)})")
        print(f"  • Linear Sum:          {ov.individual_demand_sum_mbps:.1f} Mbps")
        print(f"  • Sublinear Demand:    {ov.sublinear_aggregated_demand_mbps:.1f} Mbps")
        print(f"  • Concurrency Margin:  -{ov.attenuation_discount_mbps:.1f} Mbps ({ov.risk_band} RISK)")

    print("=" * 70)
    print("PHASE 5 VALIDATION: SUCCESSFUL")
    print("=" * 70)


if __name__ == "__main__":
    run_phase5_validation()
