from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.twinnode.node_agent.worker import NodeWorker
from agents.twinnode.tasks.registry import DisallowedTaskError, execute_allowlisted_task
from apps.api.app.core.database import utc_iso, utc_now


def test_node_auth_standby_activation_and_telemetry_separation(client: TestClient) -> None:
    # Unauthenticated registration rejected
    bad_reg = client.post(
        "/api/v1/nodes/register",
        json={"node_id": "NODE-JUNAID", "hostname": "junaid-win11"},
    )
    assert bad_reg.status_code == 401

    # Valid registration enters STANDBY
    reg = client.post(
        "/api/v1/nodes/register",
        json={"node_id": "NODE-JUNAID", "hostname": "junaid-win11", "worker_slots": 2},
        headers={"X-Node-Token": "test-token-junaid"},
    )
    assert reg.status_code == 200
    assert reg.json()["status"] == "STANDBY"

    # Standby node cannot receive tasks
    standby_task = client.post(
        "/api/v1/tasks",
        json={
            "idempotency_key": "k-standby-1",
            "task_type": "traffic_batch",
            "assigned_node_id": "NODE-JUNAID",
            "seed": 42,
        },
    )
    assert standby_task.status_code == 409

    # Activate moves to ACTIVATING and waits for worker readiness via heartbeat
    act = client.post("/api/v1/nodes/NODE-JUNAID/activate", json={"operator_id": "op1"})
    assert act.status_code == 200
    assert act.json()["status"] == "ACTIVATING"

    hb1 = client.post(
        "/api/v1/nodes/NODE-JUNAID/heartbeat",
        json={
            "cpu_pct": 22.5,
            "memory_pct": 48.1,
            "worker_active": False,
            "worker_slots": 2,
            "active_tasks": 0,
            "local_rtt_ms": 3.4,
        },
        headers={"X-Node-Token": "test-token-junaid"},
    )
    assert hb1.status_code == 200
    assert hb1.json()["desired_command"] == "ACTIVATE"
    assert hb1.json()["node"]["status"] == "ACTIVATING"

    # Once worker reports worker_active=True -> becomes ACTIVE
    hb2 = client.post(
        "/api/v1/nodes/NODE-JUNAID/heartbeat",
        json={
            "cpu_pct": 24.0,
            "memory_pct": 48.5,
            "worker_active": True,
            "worker_slots": 2,
            "active_tasks": 0,
            "local_rtt_ms": 2.9,
        },
        headers={"X-Node-Token": "test-token-junaid"},
    )
    assert hb2.status_code == 200
    node_data = hb2.json()["node"]
    assert node_data["status"] == "ACTIVE"
    assert node_data["latest_host_telemetry"]["label"] == "PHYSICAL HOST TELEMETRY — NOT CELLULAR KPI"
    assert node_data["latest_host_telemetry"]["cpu_pct"] == 24.0


def test_disallowed_task_idempotency_and_checksum_validation(client: TestClient) -> None:
    with pytest.raises(DisallowedTaskError):
        execute_allowlisted_task("rm_rf_arbitrary", 42, {})

    # Register & activate NODE-JUNAID
    client.post(
        "/api/v1/nodes/register",
        json={"node_id": "NODE-JUNAID", "hostname": "junaid-win11"},
        headers={"X-Node-Token": "test-token-junaid"},
    )
    client.post("/api/v1/nodes/NODE-JUNAID/activate", json={"operator_id": "op1"})
    client.post(
        "/api/v1/nodes/NODE-JUNAID/heartbeat",
        json={"cpu_pct": 12.0, "memory_pct": 40.0, "worker_active": True, "worker_slots": 2, "local_rtt_ms": 1.2},
        headers={"X-Node-Token": "test-token-junaid"},
    )

    # Disallowed task rejected by API schema (422)
    bad_task = client.post(
        "/api/v1/tasks",
        json={
            "idempotency_key": "bad-1",
            "task_type": "powershell_exec",
            "assigned_node_id": "NODE-JUNAID",
        },
    )
    assert bad_task.status_code == 422

    # Idempotent dispatch returns exact same task_id
    t1 = client.post(
        "/api/v1/tasks",
        json={
            "idempotency_key": "idem-unique-99",
            "task_type": "traffic_batch",
            "assigned_node_id": "NODE-JUNAID",
            "seed": 42,
            "payload": {"ticks": 2},
        },
    )
    assert t1.status_code == 200
    t2 = client.post(
        "/api/v1/tasks",
        json={
            "idempotency_key": "idem-unique-99",
            "task_type": "traffic_batch",
            "assigned_node_id": "NODE-JUNAID",
            "seed": 42,
            "payload": {"ticks": 2},
        },
    )
    assert t2.status_code == 200
    assert t1.json()["task_id"] == t2.json()["task_id"]

    # Tampered checksum rejected with 400 and task remains ASSIGNED
    task_id = t1.json()["task_id"]
    bad_res = client.post(
        f"/api/v1/tasks/{task_id}/result",
        json={
            "node_id": "NODE-JUNAID",
            "status": "COMPLETED",
            "checksum": "sha256:" + ("a" * 64),
            "result": {"task_type": "traffic_batch", "peak_demand_mbps": 500.0},
            "duration_ms": 15.0,
        },
        headers={"X-Node-Token": "test-token-junaid"},
    )
    assert bad_res.status_code == 400
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "ASSIGNED"


def test_disconnect_and_lease_timeout_recovery(client: TestClient) -> None:
    client.post(
        "/api/v1/nodes/register",
        json={"node_id": "NODE-JUNAID", "hostname": "junaid-win11"},
        headers={"X-Node-Token": "test-token-junaid"},
    )
    client.post("/api/v1/nodes/NODE-JUNAID/activate", json={"operator_id": "op1"})
    client.post(
        "/api/v1/nodes/NODE-JUNAID/heartbeat",
        json={"cpu_pct": 10.0, "memory_pct": 35.0, "worker_active": True, "worker_slots": 2, "local_rtt_ms": 1.0},
        headers={"X-Node-Token": "test-token-junaid"},
    )

    task = client.post(
        "/api/v1/tasks",
        json={
            "idempotency_key": "disconnect-test-1",
            "task_type": "scenario_evaluation",
            "assigned_node_id": "NODE-JUNAID",
            "seed": 42,
        },
    ).json()

    # Simulate elapsed heartbeat timeout in DB
    stale_ts = utc_iso(utc_now() - timedelta(seconds=30))
    with client.app.state.container.db.transaction() as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE physical_nodes SET last_heartbeat = ? WHERE node_id = ?",
            (stale_ts, "NODE-JUNAID"),
        )

    sweep = client.post("/api/v1/nodes/sweep-timeouts").json()
    assert sweep["nodes_marked_offline"] == 1
    assert sweep["tasks_moved_to_recovery"] == 1

    nodes = client.get("/api/v1/nodes").json()
    assert nodes[0]["status"] == "OFFLINE"

    # Task must NOT be completed; it moves to RETRY_PENDING
    task_after = client.get(f"/api/v1/tasks/{task['task_id']}").json()
    assert task_after["status"] == "RETRY_PENDING"
    assert task_after["retry_count"] == 1

    # Reconnect heartbeat restores node state
    reconn = client.post(
        "/api/v1/nodes/NODE-JUNAID/heartbeat",
        json={"cpu_pct": 10.0, "memory_pct": 35.0, "worker_active": True, "worker_slots": 2, "local_rtt_ms": 1.1},
        headers={"X-Node-Token": "test-token-junaid"},
    )
    assert reconn.status_code == 200
    assert reconn.json()["node"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_node_worker_executes_allowlisted_task_end_to_end(test_settings) -> None:
    from apps.api.app.main import create_app
    from simulation.seed_network import seed_network_if_needed

    app = create_app(settings=test_settings)
    seed_network_if_needed(app.state.container.network_repo, seed=42, cell_count=100, force=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        worker = NodeWorker(
            node_id="NODE-JUNAID",
            node_token="test-token-junaid",
            controller_url="http://testserver",
            http_client=async_client,
        )
        await worker.register()
        await worker.send_heartbeat()

        act_resp = await async_client.post(
            "/api/v1/nodes/NODE-JUNAID/activate",
            json={"operator_id": "op1"},
        )
        assert act_resp.status_code == 200

        # Heartbeat pulls ACTIVATE command
        hb1 = await worker.send_heartbeat()
        assert hb1["desired_command"] == "ACTIVATE"
        assert worker.worker_active is True

        # Second heartbeat confirms worker_active=True -> node becomes ACTIVE
        hb2 = await worker.send_heartbeat()
        assert hb2["node"]["status"] == "ACTIVE"

        # Dispatch counterfactual_batch task
        t_resp = await async_client.post(
            "/api/v1/tasks",
            json={
                "idempotency_key": "worker-e2e-task-1",
                "task_type": "counterfactual_batch",
                "assigned_node_id": "NODE-JUNAID",
                "seed": 42,
                "payload": {"horizon_ticks": 4},
            },
        )
        assert t_resp.status_code == 200
        task_id = t_resp.json()["task_id"]

        # Worker heartbeat pulls ASSIGNED task and spawns execution
        await worker.send_heartbeat()
        await asyncio.gather(*list(worker._background_jobs))

        final_task = (await async_client.get(f"/api/v1/tasks/{task_id}")).json()
        assert final_task["status"] == "COMPLETED"
        assert final_task["checksum"].startswith("sha256:")
        assert final_task["result"]["task_type"] == "counterfactual_batch"
        assert "baseline_congested_cell_minutes" in final_task["result"]
        await worker.shutdown()
    app.state.container.db.close()
