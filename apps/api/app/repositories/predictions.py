from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso
from apps.api.app.schemas.predictions import CellRiskRecord, ForecastRecord, RiskDriver


class PredictionRepository:
    """SQLite persistence for synthetic traffic/latency forecasts and rule-based risk assessments."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_forecasts_and_risks(
        self,
        run_id: UUID,
        state_version: int,
        forecasts: list[ForecastRecord],
        risks: list[CellRiskRecord],
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM forecasts WHERE run_id = ? AND state_version = ?",
                (str(run_id), state_version),
            )
            conn.execute(
                "DELETE FROM risk_assessments WHERE run_id = ? AND state_version = ?",
                (str(run_id), state_version),
            )
            conn.executemany(
                """
                INSERT INTO forecasts (
                    run_id, event_id, state_version, seed, cell_id, horizon_min,
                    metric, unit, predicted_value, p10, p50, p90, method,
                    model_version, data_provenance, generated_at, target_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(f.run_id),
                        str(f.event_id) if f.event_id else None,
                        f.state_version,
                        f.seed,
                        f.cell_id,
                        f.horizon_min,
                        f.metric,
                        f.unit,
                        f.predicted_value,
                        f.p10,
                        f.p50,
                        f.p90,
                        f.method,
                        f.model_version,
                        f.data_provenance,
                        utc_iso(f.generated_at),
                        utc_iso(f.target_at),
                    )
                    for f in forecasts
                ],
            )
            conn.executemany(
                """
                INSERT INTO risk_assessments (
                    run_id, event_id, state_version, cell_id, risk_band, risk_method,
                    probability, current_utilisation_pct, forecast_utilisation_pct,
                    current_latency_ms, forecast_latency_ms, drivers_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(r.run_id),
                        str(r.event_id) if r.event_id else None,
                        r.state_version,
                        r.cell_id,
                        r.risk_band,
                        r.risk_method,
                        r.probability,
                        r.current_utilisation_pct,
                        r.forecast_utilisation_pct,
                        r.current_latency_ms,
                        r.forecast_latency_ms,
                        json.dumps([d.model_dump(mode="json") for d in r.drivers]),
                        utc_iso(r.generated_at),
                    )
                    for r in risks
                ],
            )

    def _row_to_forecast(self, row: Any) -> ForecastRecord:
        return ForecastRecord(
            run_id=UUID(row["run_id"]),
            event_id=UUID(row["event_id"]) if row["event_id"] else None,
            state_version=int(row["state_version"]),
            seed=int(row["seed"]),
            cell_id=row["cell_id"],
            horizon_min=int(row["horizon_min"]),
            metric=row["metric"],
            unit=row["unit"],
            predicted_value=float(row["predicted_value"]),
            p10=float(row["p10"]) if row["p10"] is not None else None,
            p50=float(row["p50"]) if row["p50"] is not None else None,
            p90=float(row["p90"]) if row["p90"] is not None else None,
            method=row["method"],
            model_version=row["model_version"],
            data_provenance=row["data_provenance"],
            generated_at=parse_utc(row["generated_at"]),
            target_at=parse_utc(row["target_at"]),
        )

    def _row_to_risk(self, row: Any) -> CellRiskRecord:
        return CellRiskRecord(
            run_id=UUID(row["run_id"]),
            event_id=UUID(row["event_id"]) if row["event_id"] else None,
            state_version=int(row["state_version"]),
            cell_id=row["cell_id"],
            risk_band=row["risk_band"],
            risk_method=row["risk_method"],
            probability=float(row["probability"]) if row["probability"] is not None else None,
            current_utilisation_pct=float(row["current_utilisation_pct"]),
            forecast_utilisation_pct=float(row["forecast_utilisation_pct"]),
            current_latency_ms=float(row["current_latency_ms"]),
            forecast_latency_ms=float(row["forecast_latency_ms"]),
            drivers=[RiskDriver(**d) for d in json.loads(row["drivers_json"])],
            generated_at=parse_utc(row["generated_at"]),
        )

    def get_latest_for_run(
        self, run_id: UUID | str
    ) -> tuple[list[ForecastRecord], list[CellRiskRecord]]:
        latest = self.db.fetchone(
            "SELECT MAX(state_version) AS max_sv FROM forecasts WHERE run_id = ?",
            (str(run_id),),
        )
        if not latest or latest["max_sv"] is None:
            return [], []
        sv = int(latest["max_sv"])
        f_rows = self.db.fetchall(
            "SELECT * FROM forecasts WHERE run_id = ? AND state_version = ? ORDER BY cell_id ASC, horizon_min ASC, metric ASC",
            (str(run_id), sv),
        )
        r_rows = self.db.fetchall(
            "SELECT * FROM risk_assessments WHERE run_id = ? AND state_version = ? ORDER BY cell_id ASC",
            (str(run_id), sv),
        )
        return [self._row_to_forecast(r) for r in f_rows], [self._row_to_risk(r) for r in r_rows]

    def get_forecasts_for_cell(
        self, cell_id: str, run_id: UUID | str | None = None
    ) -> list[ForecastRecord]:
        if run_id:
            latest = self.db.fetchone(
                "SELECT MAX(state_version) AS max_sv FROM forecasts WHERE run_id = ?",
                (str(run_id),),
            )
            sv = int(latest["max_sv"]) if latest and latest["max_sv"] is not None else None
            if sv is None:
                return []
            rows = self.db.fetchall(
                """
                SELECT * FROM forecasts
                WHERE run_id = ? AND state_version = ? AND cell_id = ?
                ORDER BY horizon_min ASC, metric ASC
                """,
                (str(run_id), sv, cell_id),
            )
        else:
            rows = self.db.fetchall(
                """
                SELECT * FROM forecasts
                WHERE cell_id = ?
                ORDER BY generated_at DESC, horizon_min ASC
                LIMIT 50
                """,
                (cell_id,),
            )
        return [self._row_to_forecast(r) for r in rows]

    def get_forecast_history(
        self, cell_id: str | None = None, limit: int = 100
    ) -> list[ForecastRecord]:
        if cell_id:
            rows = self.db.fetchall(
                """
                SELECT * FROM forecasts
                WHERE cell_id = ?
                ORDER BY generated_at DESC, horizon_min ASC
                LIMIT ?
                """,
                (cell_id, limit),
            )
        else:
            rows = self.db.fetchall(
                """
                SELECT * FROM forecasts
                ORDER BY generated_at DESC, cell_id ASC, horizon_min ASC
                LIMIT ?
                """,
                (limit,),
            )
        return [self._row_to_forecast(r) for r in rows]

    def get_risks_for_run(
        self, run_id: UUID | str
    ) -> list[CellRiskRecord]:
        latest = self.db.fetchone(
            "SELECT MAX(state_version) AS max_sv FROM risk_assessments WHERE run_id = ?",
            (str(run_id),),
        )
        if not latest or latest["max_sv"] is None:
            return []
        sv = int(latest["max_sv"])
        rows = self.db.fetchall(
            "SELECT * FROM risk_assessments WHERE run_id = ? AND state_version = ? ORDER BY cell_id ASC",
            (str(run_id), sv),
        )
        return [self._row_to_risk(r) for r in rows]
