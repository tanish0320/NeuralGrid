from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.simulations import CellTelemetryRecord, LatencyComponents, SimulationStatus


@dataclass
class SimulationRunRow:
    id: UUID
    network_id: UUID
    seed: int
    config: dict[str, Any]
    tick: int
    state_version: int
    status: SimulationStatus
    active_event_id: UUID | None
    event_intensity: float
    attendance_scenario: str
    faults: dict[str, Any]
    applied_transfers: list[dict[str, Any]]
    sim_time_utc: datetime
    created_at: datetime
    updated_at: datetime


class SimulationRepository:
    """SQLite persistence for simulation runs and per-tick cell telemetry."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_run(
        self,
        *,
        run_id: UUID,
        network_id: UUID,
        seed: int,
        config: dict[str, Any],
        sim_time_utc: datetime,
    ) -> SimulationRunRow:
        now = utc_now()
        now_iso = utc_iso(now)
        sim_iso = utc_iso(sim_time_utc)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO simulation_runs (
                    id, network_id, seed, config_json, tick, state_version, status,
                    active_event_id, event_intensity, attendance_scenario, faults_json,
                    applied_transfers_json, sim_time_utc, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 1, 'CREATED', NULL, 1.0, 'EXPECTED', '{}', '[]', ?, ?, ?)
                """,
                (str(run_id), str(network_id), seed, json.dumps(config), sim_iso, now_iso, now_iso),
            )
        return self.get_run(run_id)  # type: ignore[return-value]

    def _row_to_run(self, row: Any) -> SimulationRunRow:
        return SimulationRunRow(
            id=UUID(row["id"]),
            network_id=UUID(row["network_id"]),
            seed=int(row["seed"]),
            config=json.loads(row["config_json"]),
            tick=int(row["tick"]),
            state_version=int(row["state_version"]),
            status=row["status"],
            active_event_id=UUID(row["active_event_id"]) if row["active_event_id"] else None,
            event_intensity=float(row["event_intensity"]),
            attendance_scenario=row["attendance_scenario"],
            faults=json.loads(row["faults_json"]),
            applied_transfers=json.loads(row["applied_transfers_json"]),
            sim_time_utc=parse_utc(row["sim_time_utc"]),
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def get_run(self, run_id: UUID | str) -> SimulationRunRow | None:
        row = self.db.fetchone("SELECT * FROM simulation_runs WHERE id = ?", (str(run_id),))
        return self._row_to_run(row) if row else None

    def list_runs(self) -> list[SimulationRunRow]:
        rows = self.db.fetchall("SELECT * FROM simulation_runs ORDER BY created_at DESC")
        return [self._row_to_run(r) for r in rows]

    def update_run_fields(
        self,
        run_id: UUID | str,
        *,
        tick: int | None = None,
        state_version: int | None = None,
        status: SimulationStatus | None = None,
        active_event_id: UUID | None | str = "__UNCHANGED__",
        event_intensity: float | None = None,
        attendance_scenario: str | None = None,
        faults: dict[str, Any] | None = None,
        applied_transfers: list[dict[str, Any]] | None = None,
        sim_time_utc: datetime | None = None,
    ) -> SimulationRunRow:
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(f"Simulation run {run_id} not found")

        new_tick = tick if tick is not None else current.tick
        new_sv = state_version if state_version is not None else current.state_version
        new_status = status if status is not None else current.status
        if active_event_id == "__UNCHANGED__":
            new_event_id = str(current.active_event_id) if current.active_event_id else None
        else:
            new_event_id = str(active_event_id) if active_event_id is not None else None
        new_intensity = event_intensity if event_intensity is not None else current.event_intensity
        new_scenario = attendance_scenario if attendance_scenario is not None else current.attendance_scenario
        new_faults = faults if faults is not None else current.faults
        new_transfers = applied_transfers if applied_transfers is not None else current.applied_transfers
        new_sim_time = sim_time_utc if sim_time_utc is not None else current.sim_time_utc
        now_iso = utc_iso(utc_now())

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE simulation_runs SET
                    tick = ?, state_version = ?, status = ?, active_event_id = ?,
                    event_intensity = ?, attendance_scenario = ?, faults_json = ?,
                    applied_transfers_json = ?, sim_time_utc = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_tick,
                    new_sv,
                    new_status,
                    new_event_id,
                    new_intensity,
                    new_scenario,
                    json.dumps(new_faults),
                    json.dumps(new_transfers),
                    utc_iso(new_sim_time),
                    now_iso,
                    str(run_id),
                ),
            )
        return self.get_run(run_id)  # type: ignore[return-value]

    def save_telemetry(self, records: list[CellTelemetryRecord]) -> None:
        if not records:
            return
        with self.db.transaction() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO telemetry (
                    run_id, tick, state_version, cell_id, background_demand_mbps,
                    event_demand_mbps, demand_mbps, served_mbps, queued_mbps,
                    unserved_mbps, utilisation_pct, simulated_latency_ms,
                    latency_components_json, packet_loss_pct, energy_units,
                    cell_state, sim_time_utc, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(r.run_id),
                        r.tick,
                        r.state_version,
                        r.cell_id,
                        r.background_demand_mbps,
                        r.event_demand_mbps,
                        r.demand_mbps,
                        r.served_mbps,
                        r.queued_mbps,
                        r.unserved_mbps,
                        r.utilisation_pct,
                        r.simulated_latency_ms,
                        r.latency_components.model_dump_json(),
                        r.packet_loss_pct,
                        r.energy_units,
                        r.cell_state,
                        utc_iso(r.sim_time_utc),
                        utc_iso(r.recorded_at),
                    )
                    for r in records
                ],
            )

    def _row_to_telemetry(self, r: Any) -> CellTelemetryRecord:
        comp = json.loads(r["latency_components_json"])
        return CellTelemetryRecord(
            run_id=UUID(r["run_id"]),
            tick=int(r["tick"]),
            state_version=int(r["state_version"]),
            cell_id=r["cell_id"],
            background_demand_mbps=float(r["background_demand_mbps"]),
            event_demand_mbps=float(r["event_demand_mbps"]),
            demand_mbps=float(r["demand_mbps"]),
            served_mbps=float(r["served_mbps"]),
            queued_mbps=float(r["queued_mbps"]),
            unserved_mbps=float(r["unserved_mbps"]),
            utilisation_pct=float(r["utilisation_pct"]),
            simulated_latency_ms=float(r["simulated_latency_ms"]),
            latency_components=LatencyComponents(**comp),
            packet_loss_pct=float(r["packet_loss_pct"]),
            energy_units=float(r["energy_units"]),
            cell_state=r["cell_state"],
            sim_time_utc=parse_utc(r["sim_time_utc"]),
            recorded_at=parse_utc(r["recorded_at"]),
        )

    def get_tick_telemetry(self, run_id: UUID | str, tick: int) -> list[CellTelemetryRecord]:
        rows = self.db.fetchall(
            "SELECT * FROM telemetry WHERE run_id = ? AND tick = ? ORDER BY cell_id ASC",
            (str(run_id), tick),
        )
        return [self._row_to_telemetry(r) for r in rows]

    def get_cell_history(
        self, run_id: UUID | str, cell_id: str | None = None, limit: int = 500
    ) -> list[CellTelemetryRecord]:
        if cell_id:
            rows = self.db.fetchall(
                "SELECT * FROM telemetry WHERE run_id = ? AND cell_id = ? ORDER BY tick ASC LIMIT ?",
                (str(run_id), cell_id, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM telemetry WHERE run_id = ? ORDER BY tick DESC, cell_id ASC LIMIT ?",
                (str(run_id), limit),
            )
        return [self._row_to_telemetry(r) for r in rows]

    def clear_telemetry(self, run_id: UUID | str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM telemetry WHERE run_id = ?", (str(run_id),))
            conn.execute("DELETE FROM event_impacts WHERE simulation_id = ?", (str(run_id),))
