from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.twinnode import (
    HostTelemetryRecord,
    NodeRecord,
    NodeStatus,
    TaskRecord,
    TaskStatus,
)


class TwinNodeRepository:
    """SQLite persistence for TwinNode physical agents, host telemetry, and tasks."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_node(
        self,
        *,
        node_id: str,
        hostname: str,
        ip_last_seen: str,
        agent_url: str | None,
        status: NodeStatus,
        agent_version: str,
        capabilities: list[str],
        worker_slots: int,
        capacity_estimate_score: float,
    ) -> NodeRecord:
        now_iso = utc_iso(utc_now())
        existing = self.db.fetchone(
            "SELECT registered_at FROM physical_nodes WHERE node_id = ?", (node_id,)
        )
        reg_iso = existing["registered_at"] if existing else now_iso
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO physical_nodes (
                    node_id, hostname, ip_last_seen, agent_url, status, agent_version,
                    capabilities_json, worker_slots, worker_active, desired_command,
                    capacity_estimate_score, last_heartbeat, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'NONE', ?, ?, ?)
                """,
                (
                    node_id,
                    hostname,
                    ip_last_seen,
                    agent_url,
                    status,
                    agent_version,
                    json.dumps(capabilities),
                    worker_slots,
                    capacity_estimate_score,
                    now_iso,
                    reg_iso,
                ),
            )
        return self.get_node(node_id)  # type: ignore[return-value]

    def _row_to_telemetry(self, row: Any) -> HostTelemetryRecord:
        return HostTelemetryRecord(
            node_id=row["node_id"],
            timestamp=parse_utc(row["timestamp"]),
            cpu_pct=float(row["cpu_pct"]),
            memory_pct=float(row["memory_pct"]),
            worker_active=bool(row["worker_active"]),
            worker_slots=int(row["worker_slots"]),
            active_tasks=int(row["active_tasks"]),
            local_rtt_ms=float(row["local_rtt_ms"]),
        )

    def _row_to_node(self, row: Any) -> NodeRecord:
        last_hb = parse_utc(row["last_heartbeat"])
        age = max(0.0, (utc_now() - last_hb).total_seconds())
        t_row = self.db.fetchone(
            "SELECT * FROM node_telemetry WHERE node_id = ? ORDER BY id DESC LIMIT 1",
            (row["node_id"],),
        )
        return NodeRecord(
            node_id=row["node_id"],
            hostname=row["hostname"],
            ip_last_seen=row["ip_last_seen"],
            agent_url=row["agent_url"],
            status=row["status"],
            agent_version=row["agent_version"],
            capabilities=json.loads(row["capabilities_json"]),
            worker_slots=int(row["worker_slots"]),
            worker_active=bool(row["worker_active"]),
            desired_command=row["desired_command"],
            capacity_estimate_score=float(row["capacity_estimate_score"]),
            last_heartbeat=last_hb,
            heartbeat_age_seconds=round(age, 2),
            registered_at=parse_utc(row["registered_at"]),
            latest_host_telemetry=self._row_to_telemetry(t_row) if t_row else None,
        )

    def get_node(self, node_id: str) -> NodeRecord | None:
        row = self.db.fetchone("SELECT * FROM physical_nodes WHERE node_id = ?", (node_id,))
        return self._row_to_node(row) if row else None

    def list_nodes(self) -> list[NodeRecord]:
        rows = self.db.fetchall("SELECT * FROM physical_nodes ORDER BY node_id ASC")
        return [self._row_to_node(r) for r in rows]

    def record_heartbeat(
        self,
        *,
        node_id: str,
        cpu_pct: float,
        memory_pct: float,
        worker_active: bool,
        worker_slots: int,
        active_tasks: int,
        local_rtt_ms: float,
        new_status: NodeStatus,
        ip_last_seen: str | None = None,
        agent_url: str | None = None,
        clear_desired_command: bool = False,
    ) -> NodeRecord:
        now_iso = utc_iso(utc_now())
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE physical_nodes SET
                    status = ?,
                    worker_active = ?,
                    worker_slots = ?,
                    last_heartbeat = ?,
                    ip_last_seen = COALESCE(?, ip_last_seen),
                    agent_url = COALESCE(?, agent_url),
                    desired_command = CASE WHEN ? THEN 'NONE' ELSE desired_command END
                WHERE node_id = ?
                """,
                (
                    new_status,
                    1 if worker_active else 0,
                    worker_slots,
                    now_iso,
                    ip_last_seen,
                    agent_url,
                    1 if clear_desired_command else 0,
                    node_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO node_telemetry (
                    node_id, timestamp, cpu_pct, memory_pct, worker_active,
                    worker_slots, active_tasks, local_rtt_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    now_iso,
                    cpu_pct,
                    memory_pct,
                    1 if worker_active else 0,
                    worker_slots,
                    active_tasks,
                    local_rtt_ms,
                ),
            )
        return self.get_node(node_id)  # type: ignore[return-value]

    def update_node_status(
        self,
        node_id: str,
        status: NodeStatus,
        *,
        desired_command: str | None = None,
        worker_active: bool | None = None,
    ) -> NodeRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE physical_nodes SET
                    status = ?,
                    desired_command = COALESCE(?, desired_command),
                    worker_active = COALESCE(?, worker_active)
                WHERE node_id = ?
                """,
                (
                    status,
                    desired_command,
                    (1 if worker_active else 0) if worker_active is not None else None,
                    node_id,
                ),
            )
        return self.get_node(node_id)  # type: ignore[return-value]

    def _row_to_task(self, row: Any) -> TaskRecord:
        return TaskRecord(
            task_id=UUID(row["task_id"]),
            idempotency_key=row["idempotency_key"],
            task_type=row["task_type"],
            schema_version=row["schema_version"],
            status=row["status"],
            origin_node_id=row["origin_node_id"],
            assigned_node_id=row["assigned_node_id"],
            plan_id=UUID(row["plan_id"]) if row["plan_id"] else None,
            simulation_id=UUID(row["simulation_id"]) if row["simulation_id"] else None,
            event_id=UUID(row["event_id"]) if row["event_id"] else None,
            seed=int(row["seed"]),
            payload=json.loads(row["payload_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            checksum=row["checksum"],
            retry_count=int(row["retry_count"]),
            lease_until=parse_utc(row["lease_until"]) if row["lease_until"] else None,
            error_message=row["error_message"],
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def create_task(self, task: TaskRecord) -> TaskRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, idempotency_key, task_type, schema_version, status,
                    origin_node_id, assigned_node_id, plan_id, simulation_id, event_id,
                    seed, payload_json, result_json, checksum, retry_count,
                    lease_until, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(task.task_id),
                    task.idempotency_key,
                    task.task_type,
                    task.schema_version,
                    task.status,
                    task.origin_node_id,
                    task.assigned_node_id,
                    str(task.plan_id) if task.plan_id else None,
                    str(task.simulation_id) if task.simulation_id else None,
                    str(task.event_id) if task.event_id else None,
                    task.seed,
                    json.dumps(task.payload, default=str),
                    json.dumps(task.result, default=str) if task.result is not None else None,
                    task.checksum,
                    task.retry_count,
                    utc_iso(task.lease_until) if task.lease_until else None,
                    task.error_message,
                    utc_iso(task.created_at),
                    utc_iso(task.updated_at),
                ),
            )
        return self.get_task(task.task_id)  # type: ignore[return-value]

    def get_task(self, task_id: UUID | str) -> TaskRecord | None:
        row = self.db.fetchone("SELECT * FROM tasks WHERE task_id = ?", (str(task_id),))
        return self._row_to_task(row) if row else None

    def get_task_by_idempotency_key(self, idempotency_key: str) -> TaskRecord | None:
        row = self.db.fetchone(
            "SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
        )
        return self._row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        plan_id: UUID | str | None = None,
        node_id: str | None = None,
    ) -> list[TaskRecord]:
        if plan_id:
            rows = self.db.fetchall(
                "SELECT * FROM tasks WHERE plan_id = ? ORDER BY created_at DESC",
                (str(plan_id),),
            )
        elif node_id:
            rows = self.db.fetchall(
                "SELECT * FROM tasks WHERE assigned_node_id = ? ORDER BY created_at DESC",
                (node_id,),
            )
        else:
            rows = self.db.fetchall("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100")
        return [self._row_to_task(r) for r in rows]

    def list_assigned_tasks_for_node(self, node_id: str) -> list[TaskRecord]:
        rows = self.db.fetchall(
            """
            SELECT * FROM tasks
            WHERE assigned_node_id = ? AND status IN ('ASSIGNED', 'RETRY_PENDING')
            ORDER BY created_at ASC
            """,
            (node_id,),
        )
        return [self._row_to_task(r) for r in rows]

    def count_active_tasks_for_node(self, node_id: str) -> int:
        row = self.db.fetchone(
            """
            SELECT COUNT(*) AS cnt FROM tasks
            WHERE assigned_node_id = ? AND status IN ('ASSIGNED', 'ACCEPTED', 'RUNNING')
            """,
            (node_id,),
        )
        return int(row["cnt"]) if row else 0

    def update_task(
        self,
        task_id: UUID | str,
        *,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        checksum: str | None = None,
        retry_count: int | None = None,
        lease_until: datetime | None | str = "__UNCHANGED__",
        error_message: str | None = None,
    ) -> TaskRecord:
        existing = self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Task {task_id} not found")

        new_retry = retry_count if retry_count is not None else existing.retry_count
        if lease_until == "__UNCHANGED__":
            new_lease = utc_iso(existing.lease_until) if existing.lease_until else None
        else:
            new_lease = utc_iso(lease_until) if isinstance(lease_until, datetime) else lease_until

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks SET
                    status = ?,
                    result_json = COALESCE(?, result_json),
                    checksum = COALESCE(?, checksum),
                    retry_count = ?,
                    lease_until = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    status,
                    json.dumps(result, default=str) if result is not None else None,
                    checksum,
                    new_retry,
                    new_lease,
                    error_message,
                    utc_iso(utc_now()),
                    str(task_id),
                ),
            )
        return self.get_task(task_id)  # type: ignore[return-value]

    def list_inflight_tasks(self) -> list[TaskRecord]:
        rows = self.db.fetchall(
            "SELECT * FROM tasks WHERE status IN ('ASSIGNED', 'ACCEPTED', 'RUNNING')"
        )
        return [self._row_to_task(r) for r in rows]
