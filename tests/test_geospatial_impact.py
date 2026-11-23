from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.core.database import Database, utc_now
from apps.api.app.core.state import AppContainer
from apps.api.app.main import create_app
from apps.api.app.modules.dependency_graph.graph_builder import haversine_km
from apps.api.app.modules.event_intelligence.geospatial.engine import GeospatialImpactEngine
from apps.api.app.modules.event_intelligence.geospatial.profiles import (
    CATEGORY_PROFILES,
    compute_event_window,
    evaluate_temporal_surge_factor,
    generate_profile_sample_points,
    get_category_profile,
)
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.source_registry import SourceRegistryRepository
from apps.api.app.schemas.events import EventEvidenceRecord, EventRecord
from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord, NetworkMetadata


@pytest.fixture
def test_db(tmp_path) -> Database:
    db_file = tmp_path / "test_neuralgrid.db"
    db = Database(str(db_file))
    db.init_schema()
    return db


@pytest.fixture
def sample_network(test_db: Database) -> tuple[NetworkMetadata, list[CellRecord]]:
    net_repo = NetworkRepository(test_db)
    net_id = uuid4()
    now = utc_now()
    meta = NetworkMetadata(
        network_id=net_id,
        seed=42,
        cell_count=5,
        regions=["CBD", "Whitefield"],
        state_version=1,
        created_at=now,
    )
    # Synthetic cells near Palace Grounds (12.9988, 77.5921)
    # Cell 1: 0.5 km away
    # Cell 2: 1.8 km away
    # Cell 3: 3.2 km away
    # Cell 4: 8.0 km away (far, beyond concert 3.5km radius)
    # Cell 5: 15.0 km away in Whitefield
    cells = [
        CellRecord(
            cell_id="CELL-CBD-001",
            network_id=net_id,
            region="CBD",
            lat=13.0010,
            lon=77.5940,
            capacity_mbps=1500.0,
            backhaul_capacity_mbps=2000.0,
            base_load_mbps=300.0,
            criticality="MEDIUM",
            is_emergency=False,
            initial_state="ACTIVE",
            current_state="ACTIVE",
        ),
        CellRecord(
            cell_id="CELL-CBD-002",
            network_id=net_id,
            region="CBD",
            lat=13.0120,
            lon=77.5980,
            capacity_mbps=1200.0,
            backhaul_capacity_mbps=1500.0,
            base_load_mbps=250.0,
            criticality="MEDIUM",
            is_emergency=False,
            initial_state="ACTIVE",
            current_state="ACTIVE",
        ),
        CellRecord(
            cell_id="CELL-CBD-003",
            network_id=net_id,
            region="CBD",
            lat=13.0250,
            lon=77.6050,
            capacity_mbps=1000.0,
            backhaul_capacity_mbps=1200.0,
            base_load_mbps=200.0,
            criticality="MEDIUM",
            is_emergency=False,
            initial_state="ACTIVE",
            current_state="ACTIVE",
        ),
        CellRecord(
            cell_id="CELL-CBD-004",
            network_id=net_id,
            region="CBD",
            lat=13.0700,
            lon=77.6300,
            capacity_mbps=1000.0,
            backhaul_capacity_mbps=1200.0,
            base_load_mbps=200.0,
            criticality="MEDIUM",
            is_emergency=False,
            initial_state="ACTIVE",
            current_state="ACTIVE",
        ),
        CellRecord(
            cell_id="CELL-WF-005",
            network_id=net_id,
            region="Whitefield",
            lat=12.9800,
            lon=77.7300,
            capacity_mbps=1000.0,
            backhaul_capacity_mbps=1200.0,
            base_load_mbps=200.0,
            criticality="MEDIUM",
            is_emergency=False,
            initial_state="ACTIVE",
            current_state="ACTIVE",
        ),
    ]
    edges = [
        CellEdgeRecord(
            edge_id="EDGE-1",
            network_id=net_id,
            source_cell_id="CELL-CBD-001",
            target_cell_id="CELL-CBD-002",
            edge_type="handover_support",
            weight=0.8,
            max_transfer_mbps=400.0,
            enabled=True,
        )
    ]
    net_repo.save_network(meta, cells, edges)
    return meta, cells


@pytest.fixture
def client(test_db: Database, sample_network) -> TestClient:
    settings = Settings(neuralgrid_db_path=test_db.db_path)
    app = create_app(settings=settings)
    return TestClient(app)


# -------------------------------------------------------------------------
# Scenario 1: Canonical event with known venue maps to correct nearby cells
# -------------------------------------------------------------------------
def test_scenario_01_canonical_event_maps_to_nearby_cells(test_db: Database, sample_network):
    meta, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    event = EventRecord(
        event_id=uuid4(),
        event_key="palace-grounds-concert-2026",
        event_origin="SOURCE_DISCOVERED",
        name="Bengaluru Rock Fest 2026",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=24),
        end_at=now + timedelta(hours=28),
        attendance_low=18000,
        attendance_high=22000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    event_repo.create_event(event)

    impacts = engine.map_event_to_cells(event, cells, now)
    assert len(impacts) >= 2
    # Closest cell must have highest relevance score
    closest = impacts[0]
    assert closest.cell_id == "CELL-CBD-001"
    assert closest.geographic_distance_km < 1.0
    assert closest.geographic_relevance_score > 0.6
    assert closest.impact_category == "PRIMARY_HOTSPOT"
    assert closest.estimated_demand_delta_mbps > 50.0


# -------------------------------------------------------------------------
# Scenario 2: Cells beyond maximum influence radius receive 0 impact weight
# -------------------------------------------------------------------------
def test_scenario_02_cells_beyond_radius_receive_zero_impact(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    event = EventRecord(
        event_id=uuid4(),
        name="Indie Night",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=10),
        end_at=now + timedelta(hours=14),
        attendance_basis="OPERATOR_ASSUMPTION",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    impacts = engine.map_event_to_cells(event, cells, now)
    impacted_cell_ids = {i.cell_id for i in impacts}

    # CELL-CBD-004 is ~8km away, CELL-WF-005 is ~15km away -> both beyond concert 3.5km radius
    assert "CELL-CBD-004" not in impacted_cell_ids
    assert "CELL-WF-005" not in impacted_cell_ids


# -------------------------------------------------------------------------
# Scenario 3: Event category affects influence radius correctly
# -------------------------------------------------------------------------
def test_scenario_03_category_affects_influence_radius():
    concert = get_category_profile("CONCERT")
    sports = get_category_profile("SPORTS")
    conf = get_category_profile("TECH_CONFERENCE")
    meetup = get_category_profile("MEETUP")

    assert concert.radius_km == 3.5
    assert sports.radius_km == 4.0
    assert conf.radius_km == 2.5
    assert meetup.radius_km == 1.2
    assert sports.radius_km > concert.radius_km > conf.radius_km > meetup.radius_km


# -------------------------------------------------------------------------
# Scenario 4: Temporal surge curve reflects arrival, event, departure phases
# -------------------------------------------------------------------------
def test_scenario_04_temporal_surge_curve():
    profile = get_category_profile("CONCERT")
    start = datetime(2026, 12, 1, 18, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 12, 1, 21, 30, 0, tzinfo=timezone.utc)
    win_start, ev_start, ev_end, win_end = compute_event_window(profile, start, end)

    # 1. Before arrival window -> 0.0
    t_before = win_start - timedelta(minutes=15)
    assert evaluate_temporal_surge_factor(profile, win_start, ev_start, ev_end, win_end, t_before) == 0.0

    # 2. Arrival ramp (1 hour into 2 hour arrival window) -> positive building factor
    t_arrival = win_start + timedelta(hours=1.0)
    factor_arr = evaluate_temporal_surge_factor(profile, win_start, ev_start, ev_end, win_end, t_arrival)
    assert 0.15 < factor_arr < profile.event_peak_factor

    # 3. During event -> peak factor
    t_mid_event = ev_start + timedelta(hours=1.5)
    factor_peak = evaluate_temporal_surge_factor(profile, win_start, ev_start, ev_end, win_end, t_mid_event)
    assert factor_peak >= profile.event_peak_factor
    assert factor_peak > factor_arr

    # 4. Departure phase -> decaying factor
    t_depart = ev_end + timedelta(minutes=45)
    factor_dep = evaluate_temporal_surge_factor(profile, win_start, ev_start, ev_end, win_end, t_depart)
    assert 0.0 < factor_dep < factor_peak

    # 5. After window -> 0.0
    t_after = win_end + timedelta(minutes=15)
    assert evaluate_temporal_surge_factor(profile, win_start, ev_start, ev_end, win_end, t_after) == 0.0


# -------------------------------------------------------------------------
# Scenario 5: Missing coordinates handled gracefully (not crashing, flagged)
# -------------------------------------------------------------------------
def test_scenario_05_missing_coordinates_handled_gracefully(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    event_no_coords = EventRecord(
        event_id=uuid4(),
        name="Virtual / Unknown Locality Summit",
        event_origin="SOURCE_DISCOVERED",
        event_type="TECH_CONFERENCE",
        city="Bengaluru",
        latitude=None,
        longitude=None,
        start_at=now + timedelta(hours=5),
        end_at=now + timedelta(hours=9),
        attendance_basis="OPERATOR_ASSUMPTION",
        intensity=1.0,
        verification_status="PARTIALLY_VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    event_repo.create_event(event_no_coords)

    impacts = engine.map_event_to_cells(event_no_coords, cells, now)
    assert impacts == []  # Gracefully returns empty without crashing


# -------------------------------------------------------------------------
# Scenario 6: Missing attendance handled gracefully with category default
# -------------------------------------------------------------------------
def test_scenario_06_missing_attendance_handled_gracefully(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    event_no_att = EventRecord(
        event_id=uuid4(),
        name="Tech Unconference",
        event_origin="SOURCE_DISCOVERED",
        event_type="TECH_CONFERENCE",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=6),
        end_at=now + timedelta(hours=10),
        attendance_low=None,
        attendance_high=None,
        attendance_basis="OPERATOR_ASSUMPTION",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    impacts = engine.map_event_to_cells(event_no_att, cells, now)
    assert len(impacts) > 0
    # Uses default tech conference attendance (5000) and marks estimated
    assert impacts[0].temporal_profile["attendance_estimated"] is True
    assert impacts[0].temporal_profile["effective_attendance"] == 5000
    assert impacts[0].impact_confidence < 0.60  # Lowered due to estimated attendance


# -------------------------------------------------------------------------
# Scenario 7: Cancelled event produces zero future impact
# -------------------------------------------------------------------------
def test_scenario_07_cancelled_event_produces_zero_impact(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    cancelled_event = EventRecord(
        event_id=uuid4(),
        name="Cancelled Mega Concert",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=24),
        end_at=now + timedelta(hours=28),
        attendance_low=20000,
        attendance_high=30000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="CANCELLED",
        status="CANCELLED",
        created_at=now,
        updated_at=now,
    )
    assert engine.is_event_eligible(cancelled_event, now)[0] is False
    impacts = engine.map_event_to_cells(cancelled_event, cells, now)
    assert impacts == []


# -------------------------------------------------------------------------
# Scenario 8: Expired event excluded from future demand prediction
# -------------------------------------------------------------------------
def test_scenario_08_expired_event_excluded_from_future_prediction(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    past_event = EventRecord(
        event_id=uuid4(),
        name="Yesterday Concert",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now - timedelta(hours=30),
        end_at=now - timedelta(hours=26),
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="COMPLETED",
        created_at=now - timedelta(hours=35),
        updated_at=now - timedelta(hours=25),
    )
    eligible, reason = engine.is_event_eligible(past_event, now)
    assert eligible is False
    assert reason == "EVENT_TEMPORALLY_EXPIRED"
    assert engine.map_event_to_cells(past_event, cells, now) == []


# -------------------------------------------------------------------------
# Scenario 9: Multiple simultaneous events aggregate sub-linearly
# -------------------------------------------------------------------------
def test_scenario_09_multiple_events_aggregate_sublinearly(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    target_cell = cells[0]
    now = utc_now()

    # Two concurrent events near CELL-CBD-001
    ev1 = EventRecord(
        event_id=uuid4(),
        name="Event Alpha",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        city="Bengaluru",
        latitude=13.0010,
        longitude=77.5940,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=5),
        attendance_high=15000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    ev2 = EventRecord(
        event_id=uuid4(),
        name="Event Beta",
        event_origin="SOURCE_DISCOVERED",
        event_type="SPORTS",
        city="Bengaluru",
        latitude=13.0015,
        longitude=77.5945,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=5),
        attendance_high=20000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )

    imp1 = engine.map_event_to_cells(ev1, [target_cell], now)[0]
    imp2 = engine.map_event_to_cells(ev2, [target_cell], now)[0]

    events_map = {ev1.event_id: ev1, ev2.event_id: ev2}
    agg = engine.aggregate_cell_impacts(target_cell, [imp1, imp2], events_map)

    # Sublinear demand should be less than naive sum
    naive_sum = imp1.estimated_demand_delta_mbps + imp2.estimated_demand_delta_mbps
    assert agg.combined_demand_delta_mbps < naive_sum
    assert agg.combined_demand_delta_mbps > max(imp1.estimated_demand_delta_mbps, imp2.estimated_demand_delta_mbps)
    assert agg.contributing_event_count == 2


# -------------------------------------------------------------------------
# Scenario 10: Cell-centric view correctly aggregates multiple contributing events
# -------------------------------------------------------------------------
def test_scenario_10_cell_centric_view_aggregation(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    cell = cells[0]
    now = utc_now()
    ev = EventRecord(
        event_id=uuid4(),
        name="Concert Gamma",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        city="Bengaluru",
        latitude=13.0010,
        longitude=77.5940,
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=4),
        attendance_high=10000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    impacts = engine.map_event_to_cells(ev, [cell], now)
    agg = engine.aggregate_cell_impacts(cell, impacts, {ev.event_id: ev})

    assert agg.cell_id == cell.cell_id
    assert agg.projected_total_demand_mbps == round(cell.base_load_mbps + agg.combined_demand_delta_mbps, 2)
    assert agg.projected_utilisation_pct > 0
    assert agg.congestion_risk_band in ("NORMAL", "ELEVATED", "HIGH", "CRITICAL")
    assert len(agg.contributing_events) == 1
    assert agg.contributing_events[0].event_title == "Concert Gamma"


# -------------------------------------------------------------------------
# Scenario 11: Overlapping event detection flags cells with multiple events
# -------------------------------------------------------------------------
def test_scenario_11_overlapping_event_detection(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    ev1 = EventRecord(
        event_id=uuid4(),
        name="Festival A",
        event_origin="SOURCE_DISCOVERED",
        event_type="FESTIVAL",
        city="Bengaluru",
        latitude=13.0010,
        longitude=77.5940,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=6),
        attendance_high=12000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    ev2 = EventRecord(
        event_id=uuid4(),
        name="Concert B",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        city="Bengaluru",
        latitude=13.0020,
        longitude=77.5930,
        start_at=now + timedelta(hours=3),
        end_at=now + timedelta(hours=7),
        attendance_high=18000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )

    imp1 = engine.map_event_to_cells(ev1, cells, now)
    imp2 = engine.map_event_to_cells(ev2, cells, now)
    all_imp = imp1 + imp2
    events_map = {ev1.event_id: ev1, ev2.event_id: ev2}

    overlaps = engine.detect_overlapping_cells(cells, all_imp, events_map)
    assert len(overlaps) >= 1
    top_overlap = overlaps[0]
    assert top_overlap.overlapping_event_count >= 2
    assert top_overlap.attenuation_discount_mbps > 0.0
    assert len(top_overlap.event_titles) >= 2


# -------------------------------------------------------------------------
# Scenario 12: Recalculation correctly updates impact records on changes
# -------------------------------------------------------------------------
def test_scenario_12_recalculation_updates_impacts_on_changes(test_db: Database, sample_network):
    meta, _ = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo)

    now = utc_now()
    event_id = uuid4()
    ev = EventRecord(
        event_id=event_id,
        name="Scaling Concert",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=10),
        end_at=now + timedelta(hours=14),
        attendance_low=5000,
        attendance_high=10000,
        attendance_basis="OPERATOR_ASSUMPTION",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    event_repo.create_event(ev)

    res1 = engine.recalculate_all(meta.network_id)
    assert res1.total_impact_records > 0
    records1 = impact_repo.get_impacts_for_event(event_id)
    delta1 = records1[0].estimated_demand_delta_mbps

    # Update event attendance from 10k to 50k
    ev_updated = ev.model_copy(update={"attendance_low": 45000, "attendance_high": 55000})
    event_repo.update_event(ev_updated)

    res2 = engine.recalculate_all(meta.network_id)
    records2 = impact_repo.get_impacts_for_event(event_id)
    delta2 = records2[0].estimated_demand_delta_mbps

    assert delta2 > delta1 * 3.0  # Surge scaled up without duplicate records
    assert len(records2) == len(records1)


# -------------------------------------------------------------------------
# Scenario 13: Evidence provenance correctly retained in impact records
# -------------------------------------------------------------------------
def test_scenario_13_evidence_provenance_retained(test_db: Database, sample_network):
    _, cells = sample_network
    event_repo = EventRepository(test_db)
    impact_repo = ImpactRepository(test_db)
    reg_repo = SourceRegistryRepository(test_db)
    engine = GeospatialImpactEngine(event_repo, NetworkRepository(test_db), impact_repo, reg_repo)

    now = utc_now()
    ev_id = uuid4()
    evidence_id = "EVID-BMS-0099"

    event = EventRecord(
        event_id=ev_id,
        name="Rock Fest Verified",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=12),
        end_at=now + timedelta(hours=16),
        attendance_low=20000,
        attendance_high=25000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    event_repo.create_event(event)

    evidence = EventEvidenceRecord(
        evidence_id=evidence_id,
        event_id=ev_id,
        source_platform="bookmyshow",
        source_url="https://in.bookmyshow.com/bengaluru/events/rock-fest/ET001234",
        source_timestamp=now,
        evidence_type="TICKETING_LISTING",
        extracted_text="Bengaluru Rock Fest Palace Grounds 25000 tickets",
        source_reliability=0.92,
        evidence_confidence=0.95,
        created_at=now,
    )
    reg_repo.add_evidence(evidence)

    impacts = engine.map_event_to_cells(event, cells, now)
    assert len(impacts) > 0
    assert evidence_id in impacts[0].input_evidence_ids


# -------------------------------------------------------------------------
# Scenario 14: Database migration creates table without data loss
# -------------------------------------------------------------------------
def test_scenario_14_database_schema_idempotence(test_db: Database):
    # Calling init_schema again should not error or drop tables
    test_db.init_schema()

    # Table event_cell_impacts must exist
    row = test_db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='event_cell_impacts'")
    assert row is not None
    assert row["name"] == "event_cell_impacts"

    # Index must exist
    idx_row = test_db.fetchone("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_impacts_event'")
    assert idx_row is not None


# -------------------------------------------------------------------------
# Scenario 15: REST endpoints return correct schemas, status codes and filtering
# -------------------------------------------------------------------------
def test_scenario_15_rest_endpoints(client: TestClient, test_db: Database, sample_network):
    now = utc_now()
    event_id = uuid4()
    ev = EventRecord(
        event_id=event_id,
        name="REST API Test Concert",
        event_origin="SOURCE_DISCOVERED",
        event_type="CONCERT",
        venue_name="Palace Grounds",
        city="Bengaluru",
        latitude=12.9988,
        longitude=77.5921,
        start_at=now + timedelta(hours=20),
        end_at=now + timedelta(hours=24),
        attendance_low=10000,
        attendance_high=15000,
        attendance_basis="SOURCE_EVIDENCE",
        intensity=1.0,
        verification_status="VERIFIED",
        status="UPCOMING",
        created_at=now,
        updated_at=now,
    )
    event_repo = EventRepository(test_db)
    event_repo.create_event(ev)

    # 1. POST /impact/recalculate
    res_recalc = client.post("/api/v1/event-intelligence/impact/recalculate", json={})
    assert res_recalc.status_code == 200
    recalc_data = res_recalc.json()
    assert recalc_data["status"] == "SUCCESS"
    assert recalc_data["total_impact_records"] > 0

    # 2. GET /impact/events
    res_events = client.get("/api/v1/event-intelligence/impact/events")
    assert res_events.status_code == 200
    events_data = res_events.json()
    assert len(events_data) >= 1
    assert any(e["event_id"] == str(event_id) for e in events_data)

    # 3. GET /impact/events/{event_id}
    res_ev_detail = client.get(f"/api/v1/event-intelligence/impact/events/{event_id}")
    assert res_ev_detail.status_code == 200
    ev_detail_data = res_ev_detail.json()
    assert ev_detail_data["event_id"] == str(event_id)
    assert len(ev_detail_data["affected_cells"]) > 0

    # 4. GET /impact/cells
    res_cells = client.get("/api/v1/event-intelligence/impact/cells")
    assert res_cells.status_code == 200
    cells_data = res_cells.json()
    assert len(cells_data) == 5

    # 5. GET /impact/cells/{cell_id}
    res_cell_detail = client.get("/api/v1/event-intelligence/impact/cells/CELL-CBD-001")
    assert res_cell_detail.status_code == 200
    cell_detail = res_cell_detail.json()
    assert cell_detail["cell_id"] == "CELL-CBD-001"
    assert cell_detail["combined_demand_delta_mbps"] > 0.0

    # 6. GET /impact/overlaps
    res_overlaps = client.get("/api/v1/event-intelligence/impact/overlaps")
    assert res_overlaps.status_code == 200
    assert isinstance(res_overlaps.json(), list)
