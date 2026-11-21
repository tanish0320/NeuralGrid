from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_demand_invariant(telemetry: list[dict]) -> None:
    assert len(telemetry) == 100
    for rec in telemetry:
        total = rec["demand_mbps"]
        parts = rec["served_mbps"] + rec["queued_mbps"] + rec["unserved_mbps"]
        assert abs(total - parts) < 1e-3, f"Invariant failed for {rec['cell_id']}: {total} != {parts}"


def test_simulation_step_pause_reset_and_accounting_invariant(client: TestClient) -> None:
    sim_resp = client.post("/api/v1/simulations", json={"seed": 42, "step_minutes": 5})
    assert sim_resp.status_code == 200
    sim = sim_resp.json()
    sim_id = sim["simulation_id"]
    assert sim["tick"] == 0
    assert sim["state_version"] == 1
    _assert_demand_invariant(sim["telemetry"])

    # Step 1
    step1 = client.post(f"/api/v1/simulations/{sim_id}/step").json()
    assert step1["tick"] == 1
    assert step1["state_version"] == 2
    _assert_demand_invariant(step1["telemetry"])

    # Inject cell failure + backhaul fault and verify accounting holds
    active_cell = next(t["cell_id"] for t in step1["telemetry"] if t["cell_state"] == "ACTIVE")
    fault_resp = client.post(
        f"/api/v1/simulations/{sim_id}/faults",
        json={"fault_type": "CELL_FAILURE", "cell_id": active_cell, "severity": 1.0, "active": True},
    )
    assert fault_resp.status_code == 200
    fault_state = fault_resp.json()
    _assert_demand_invariant(fault_state["telemetry"])
    failed_rec = next(t for t in fault_state["telemetry"] if t["cell_id"] == active_cell)
    assert failed_rec["cell_state"] == "FAILED"
    assert failed_rec["served_mbps"] == 0.0

    # Pause + Reset restores tick 0 and initial states
    assert client.post(f"/api/v1/simulations/{sim_id}/pause").status_code == 200
    reset_state = client.post(f"/api/v1/simulations/{sim_id}/reset").json()
    assert reset_state["tick"] == 0
    assert reset_state["faults"] == {}
    _assert_demand_invariant(reset_state["telemetry"])
    restored_rec = next(t for t in reset_state["telemetry"] if t["cell_id"] == active_cell)
    assert restored_rec["cell_state"] == "ACTIVE"


def test_event_intensity_increases_demand_deterministically(client: TestClient) -> None:
    events = client.get("/api/v1/events").json()
    demo_ev = next(e for e in events if e["event_key"] == "palace-grounds-demo")
    event_id = demo_ev["event_id"]

    # Confirm demo assumptions
    confirm_resp = client.post(
        f"/api/v1/events/{event_id}/confirm",
        json={"operator_id": "tester", "accept_demo_assumptions": True},
    )
    assert confirm_resp.status_code == 200

    sim1 = client.post(
        "/api/v1/simulations",
        json={"seed": 42, "start_time_utc": "2026-11-21T13:00:00Z"},
    ).json()
    sim2 = client.post(
        "/api/v1/simulations",
        json={"seed": 42, "start_time_utc": "2026-11-21T13:00:00Z"},
    ).json()

    inj1 = client.post(
        f"/api/v1/simulations/{sim1['simulation_id']}/events",
        json={"event_id": event_id, "influence_radius_km": 3.0, "attendance_scenario": "EXPECTED", "intensity": 1.0},
    ).json()
    inj2 = client.post(
        f"/api/v1/simulations/{sim2['simulation_id']}/events",
        json={"event_id": event_id, "influence_radius_km": 3.0, "attendance_scenario": "EXPECTED", "intensity": 2.0},
    ).json()

    affected_ids = {c["cell_id"] for c in inj1["impact"]["affected_cells"]}
    assert len(affected_ids) > 0

    step1 = client.post(f"/api/v1/simulations/{sim1['simulation_id']}/step").json()
    step2 = client.post(f"/api/v1/simulations/{sim2['simulation_id']}/step").json()
    _assert_demand_invariant(step1["telemetry"])
    _assert_demand_invariant(step2["telemetry"])

    ev_demand_1 = sum(t["event_demand_mbps"] for t in step1["telemetry"] if t["cell_id"] in affected_ids)
    ev_demand_2 = sum(t["event_demand_mbps"] for t in step2["telemetry"] if t["cell_id"] in affected_ids)
    assert ev_demand_1 > 0
    assert ev_demand_2 > ev_demand_1 * 1.5
