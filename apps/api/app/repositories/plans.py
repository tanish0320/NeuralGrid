from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.plans import (
    ConstraintCheckResult,
    ObjectiveBreakdown,
    OperatorIntent,
    PlanActionRecord,
    PlanRecord,
    PlanStatus,
)


class PlanRepository:
    """SQLite persistence for constrained plans, actions, and operator approval decisions."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_plan(self, plan: PlanRecord) -> PlanRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO plans (
                    plan_id, run_id, event_id, seed, version, state_version, status,
                    solver_method, intent_json, objective_json, constraints_json,
                    explanation_json, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(plan.plan_id),
                    str(plan.simulation_id),
                    str(plan.event_id) if plan.event_id else None,
                    plan.seed,
                    plan.version,
                    plan.state_version,
                    plan.status,
                    plan.solver_method,
                    plan.intent.model_dump_json(),
                    plan.objective.model_dump_json(),
                    json.dumps([c.model_dump(mode="json") for c in plan.constraints_checked]),
                    json.dumps(plan.explanation),
                    utc_iso(plan.expires_at),
                    utc_iso(plan.created_at),
                    utc_iso(plan.updated_at),
                ),
            )
            conn.executemany(
                """
                INSERT INTO plan_actions (
                    action_id, plan_id, action_order, action_type, source_id,
                    target_id, amount, params_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(a.action_id),
                        str(plan.plan_id),
                        a.action_order,
                        a.action_type,
                        a.source_id,
                        a.target_id,
                        a.amount,
                        json.dumps(a.params, default=str),
                    )
                    for a in plan.actions
                ],
            )
        return self.get_plan(plan.plan_id)  # type: ignore[return-value]

    def _row_to_plan(self, row: Any, action_rows: list[Any]) -> PlanRecord:
        return PlanRecord(
            plan_id=UUID(row["plan_id"]),
            simulation_id=UUID(row["run_id"]),
            event_id=UUID(row["event_id"]) if row["event_id"] else None,
            seed=int(row["seed"]),
            version=int(row["version"]),
            state_version=int(row["state_version"]),
            status=row["status"],
            solver_method=row["solver_method"],
            intent=OperatorIntent(**json.loads(row["intent_json"])),
            objective=ObjectiveBreakdown(**json.loads(row["objective_json"])),
            constraints_checked=[
                ConstraintCheckResult(**c) for c in json.loads(row["constraints_json"])
            ],
            actions=[
                PlanActionRecord(
                    action_id=UUID(a["action_id"]),
                    action_order=int(a["action_order"]),
                    action_type=a["action_type"],
                    source_id=a["source_id"],
                    target_id=a["target_id"],
                    amount=float(a["amount"]),
                    params=json.loads(a["params_json"]),
                )
                for a in action_rows
            ],
            explanation=json.loads(row["explanation_json"]),
            expires_at=parse_utc(row["expires_at"]),
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def get_plan(self, plan_id: UUID | str) -> PlanRecord | None:
        row = self.db.fetchone("SELECT * FROM plans WHERE plan_id = ?", (str(plan_id),))
        if not row:
            return None
        actions = self.db.fetchall(
            "SELECT * FROM plan_actions WHERE plan_id = ? ORDER BY action_order ASC",
            (str(plan_id),),
        )
        return self._row_to_plan(row, actions)

    def list_plans(self, run_id: UUID | str | None = None) -> list[PlanRecord]:
        if run_id:
            rows = self.db.fetchall(
                "SELECT * FROM plans WHERE run_id = ? ORDER BY created_at DESC",
                (str(run_id),),
            )
        else:
            rows = self.db.fetchall("SELECT * FROM plans ORDER BY created_at DESC LIMIT 100")
        results: list[PlanRecord] = []
        for row in rows:
            actions = self.db.fetchall(
                "SELECT * FROM plan_actions WHERE plan_id = ? ORDER BY action_order ASC",
                (row["plan_id"],),
            )
            results.append(self._row_to_plan(row, actions))
        return results

    def update_plan_status(self, plan_id: UUID | str, status: PlanStatus) -> PlanRecord:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                (status, utc_iso(utc_now()), str(plan_id)),
            )
        return self.get_plan(plan_id)  # type: ignore[return-value]

    def record_approval(
        self,
        *,
        plan_id: UUID | str,
        operator_id: str,
        decision: str,
        reason: str | None,
        state_version: int,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO approvals (plan_id, operator_id, decision, reason, state_version, decided_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(plan_id), operator_id, decision, reason, state_version, utc_iso(utc_now())),
            )

    def mark_open_plans_stale(self, run_id: UUID | str) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE plans SET status = 'STALE', updated_at = ?
                WHERE run_id = ? AND status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED')
                """,
                (utc_iso(utc_now()), str(run_id)),
            )
            return cursor.rowcount
