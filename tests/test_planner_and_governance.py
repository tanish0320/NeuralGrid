from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.app.core.database import utc_now


def _setup_stressed_simulation(client: TestClient) -> dict:
    events = client.get("/api/v1/events").json()
    demo = next(e for e in events if e["event_key"] == "palace-grounds-demo")
    client.post(
        f"/api/v1/events/{demo['event_id']}/confirm",
        json={"operator_id": "op1", "accept_demo_assumptions": True},
    )
    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    client.post(
        f"/api/v1/simulations/{sim['simulation_id']}/events",
        json={
            "event_id": demo["event_id"],
            "influence_radius_km": 3.0,
            "attendance_scenario": "HIGH",
            "intensity": 2.0,
        },
    )
    client.post(f"/api/v1/simulations/{sim['simulation_id']}/step")
    return client.get(f"/api/v1/simulations/{sim['simulation_id']}/state").json()


def test_planner_constraints_and_determinism(client: TestClient) -> None:
    sim_state = _setup_stressed_simulation(client)
    sim_id = sim_state["simulation_id"]
    sv = sim_state["state_version"]

    p1 = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": sv}).json()
    p2 = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": sv}).json()

    assert p1["status"] == "PENDING_APPROVAL"
    assert all(c["passed"] for c in p1["constraints_checked"])
    assert len(p1["actions"]) >= 1
    assert p1["objective"]["after_projected"]["total_score"] <= p1["objective"]["before"]["total_score"]
    # Standby/absent Node B must NOT receive a compute task
    assert all(a["action_type"] != "dispatch_compute_task" for a in p1["actions"])

    # Determinism: identical action sequence for identical state
    actions1 = [(a["action_type"], a["source_id"], a["target_id"], a["amount"]) for a in p1["actions"]]
    actions2 = [(a["action_type"], a["source_id"], a["target_id"], a["amount"]) for a in p2["actions"]]
    assert actions1 == actions2


def test_governance_blocks_unapproved_rejected_stale_and_expired_plans(client: TestClient) -> None:
    sim_state = _setup_stressed_simulation(client)
    sim_id = sim_state["simulation_id"]
    sv = sim_state["state_version"]

    # 1. Unapproved plan cannot execute
    plan_a = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": sv}).json()
    exec_unapproved = client.post(
        f"/api/v1/plans/{plan_a['plan_id']}/execute",
        json={"operator_id": "op1"},
    )
    assert exec_unapproved.status_code == 409

    # 2. Rejected plan can never execute or be approved
    rej = client.post(
        f"/api/v1/plans/{plan_a['plan_id']}/reject",
        json={"operator_id": "op1", "reason": "Too aggressive"},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "REJECTED"
    assert (
        client.post(
            f"/api/v1/plans/{plan_a['plan_id']}/execute",
            json={"operator_id": "op1"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/plans/{plan_a['plan_id']}/approve",
            json={"operator_id": "op1", "plan_version": plan_a["version"], "state_version": sv},
        ).status_code
        == 409
    )

    # 3. Stale plan cannot execute after simulation state_version advances
    plan_b = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": sv}).json()
    assert (
        client.post(
            f"/api/v1/plans/{plan_b['plan_id']}/approve",
            json={"operator_id": "op1", "plan_version": plan_b["version"], "state_version": sv},
        ).status_code
        == 200
    )
    # Advance simulation tick -> state_version changes
    client.post(f"/api/v1/simulations/{sim_id}/step")
    stale_exec = client.post(
        f"/api/v1/plans/{plan_b['plan_id']}/execute",
        json={"operator_id": "op1"},
    )
    assert stale_exec.status_code == 409
    assert client.get(f"/api/v1/plans/{plan_b['plan_id']}").json()["status"] == "STALE"

    # 4. Expired plan cannot execute
    latest_sv = client.get(f"/api/v1/simulations/{sim_id}/state").json()["state_version"]
    plan_c = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": latest_sv}).json()
    client.post(
        f"/api/v1/plans/{plan_c['plan_id']}/approve",
        json={"operator_id": "op1", "plan_version": plan_c["version"], "state_version": latest_sv},
    )
    # Backdate expiry in DB directly
    past_iso = (utc_now() - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    with client.app.state.container.db.transaction() as conn:  # type: ignore[attr-defined]
        conn.execute("UPDATE plans SET expires_at = ? WHERE plan_id = ?", (past_iso, plan_c["plan_id"]))
    exp_exec = client.post(f"/api/v1/plans/{plan_c['plan_id']}/execute", json={"operator_id": "op1"})
    assert exp_exec.status_code == 409
    assert client.get(f"/api/v1/plans/{plan_c['plan_id']}").json()["status"] == "EXPIRED"

    # 5. Fresh valid plan executes cleanly
    plan_d = client.post("/api/v1/plans/generate", json={"simulation_id": sim_id, "state_version": latest_sv}).json()
    assert (
        client.post(
            f"/api/v1/plans/{plan_d['plan_id']}/approve",
            json={"operator_id": "op1", "plan_version": plan_d["version"], "state_version": latest_sv},
        ).status_code
        == 200
    )
    exec_ok = client.post(
        f"/api/v1/plans/{plan_d['plan_id']}/execute",
        json={"operator_id": "op1", "expected_state_version": latest_sv},
    )
    assert exec_ok.status_code == 200
    assert exec_ok.json()["plan"]["status"] == "COMPLETED"
