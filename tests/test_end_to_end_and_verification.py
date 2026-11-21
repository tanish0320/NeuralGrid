from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.twinnode.node_agent.worker import NodeWorker
from apps.api.app.config import Settings
from apps.api.app.main import create_app
from simulation.seed_network import seed_network_if_needed


def test_websocket_stream_emits_events(client: TestClient) -> None:
    with client.websocket_connect("/ws/live") as ws:
        hello = ws.receive_json()
        assert hello["event"] == "ws.connected"

        sim_id = client.post("/api/v1/simulations", json={"seed": 42}).json()["simulation_id"]
        client.post(f"/api/v1/simulations/{sim_id}/step")

        tick_msg = ws.receive_json()
        assert tick_msg["event"] == "tick.updated"
        assert tick_msg["data"]["simulation_id"] == sim_id


@pytest.mark.asyncio
async def test_full_end_to_end_vertical_slice_and_verification(test_settings: Settings) -> None:
    app = create_app(settings=test_settings)
    container = app.state.container
    seed_network_if_needed(container.network_repo, seed=42, cell_count=100, force=True)
    demo_event = container.event_repo.ensure_seeded_demo_event("palace-grounds-demo")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # 1. Register & activate physical Node B (NODE-JUNAID) and Node A (NODE-TANISH)
        worker_b = NodeWorker(
            node_id="NODE-JUNAID",
            node_token="test-token-junaid",
            controller_url="http://testserver",
            http_client=ac,
        )
        await worker_b.register()
        await worker_b.send_heartbeat()
        await ac.post("/api/v1/nodes/NODE-JUNAID/activate", json={"operator_id": "op1"})
        await worker_b.send_heartbeat()
        await worker_b.send_heartbeat()

        # 2. Confirm seeded Palace Grounds demo event & map impact
        ev_id = str(demo_event.event_id)
        confirm = await ac.post(
            f"/api/v1/events/{ev_id}/confirm",
            json={"operator_id": "op1", "accept_demo_assumptions": True},
        )
        assert confirm.status_code == 200

        sim = (await ac.post("/api/v1/simulations", json={"seed": 42})).json()
        sim_id = sim["simulation_id"]

        inj = await ac.post(
            f"/api/v1/simulations/{sim_id}/events",
            json={
                "event_id": ev_id,
                "influence_radius_km": 3.0,
                "attendance_scenario": "HIGH",
                "intensity": 1.8,
            },
        )
        assert inj.status_code == 200
        assert len(inj.json()["impact"]["affected_cells"]) > 0

        # 3. Step simulation & generate forecast + risk
        step = (await ac.post(f"/api/v1/simulations/{sim_id}/step")).json()
        sv = step["state_version"]
        preds = (
            await ac.post(
                "/api/v1/predictions/generate",
                json={"simulation_id": sim_id, "horizons": [15, 30]},
            )
        ).json()
        assert preds["event_id"] == ev_id

        # 4. Generate plan -> approve -> execute (dispatches TwinNode task to NODE-JUNAID)
        plan = (
            await ac.post(
                "/api/v1/plans/generate",
                json={"simulation_id": sim_id, "state_version": sv},
            )
        ).json()
        assert any(a["action_type"] == "dispatch_compute_task" and a["target_id"] == "NODE-JUNAID" for a in plan["actions"])

        app_resp = await ac.post(
            f"/api/v1/plans/{plan['plan_id']}/approve",
            json={"operator_id": "op1", "plan_version": plan["version"], "state_version": sv},
        )
        assert app_resp.status_code == 200

        exec_resp = await ac.post(
            f"/api/v1/plans/{plan['plan_id']}/execute",
            json={"operator_id": "op1", "expected_state_version": sv},
        )
        assert exec_resp.status_code == 200
        dispatched_ids = exec_resp.json()["dispatched_task_ids"]
        assert len(dispatched_ids) == 1

        # 5. Worker pulls and completes remote task
        await worker_b.send_heartbeat()
        await asyncio.gather(*list(worker_b._background_jobs))

        task_state = (await ac.get(f"/api/v1/tasks/{dispatched_ids[0]}")).json()
        assert task_state["status"] == "COMPLETED"
        assert task_state["event_id"] == ev_id

        # 6. Counterfactual verification compares matched baseline vs intervention
        ver_resp = await ac.post(
            "/api/v1/verification/run",
            json={"simulation_id": sim_id, "plan_id": plan["plan_id"], "horizon_ticks": 8},
        )
        assert ver_resp.status_code == 200
        ver = ver_resp.json()
        assert ver["config_match"] is True
        assert ver["event_id"] == ev_id
        assert ver["seed"] == 42
        assert ver["label"] == "SIMULATION COUNTERFACTUAL — NOT LIVE NETWORK OUTCOME"
        assert ver["twinnode_metrics"]["tasks_completed"] == 1
        assert "NODE-JUNAID" in ver["twinnode_metrics"]["executed_nodes"]
        assert ver["intervention"]["congested_cell_minutes"] <= ver["baseline"]["congested_cell_minutes"]

        # 7. Audit trail records complete provenance
        audit = (await ac.get("/api/v1/audit")).json()
        actions_seen = {a["action"] for a in audit}
        assert {
            "event.confirmed",
            "simulation.event_injected",
            "predictions.generated",
            "plan.generated",
            "plan.approved",
            "plan.executed",
            "task.completed",
            "verification.completed",
        }.issubset(actions_seen)

        await worker_b.shutdown()
    container.db.close()
