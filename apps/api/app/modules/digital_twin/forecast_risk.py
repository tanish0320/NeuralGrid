from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.config import Settings
from apps.api.app.core.database import utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.predictions import PredictionRepository
from apps.api.app.repositories.simulations import SimulationRepository
from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord
from apps.api.app.schemas.predictions import (
    CellRiskRecord,
    ForecastRecord,
    PredictionsResponse,
    RiskBand,
    RiskDriver,
)
from apps.api.app.schemas.simulations import CellTelemetryRecord, SimulationStateResponse
from simulation.tick_engine import temporal_profile_multiplier


class ForecastProviderProtocol(Protocol):
    """Pluggable interface so Tanish's evaluated ML predictor can replace the deterministic baseline."""

    method_name: str
    model_version: str
    data_provenance: str

    def generate_forecasts(
        self,
        *,
        sim_state: SimulationStateResponse,
        cells: dict[str, CellRecord],
        history: list[CellTelemetryRecord],
        horizons: list[int],
        target_cell_ids: list[str],
    ) -> list[ForecastRecord]: ...


class DeterministicBaselineForecastProvider:
    """Honest, transparent persistence + trend + event-profile baseline (not an ML claim)."""

    method_name = "deterministic_persistence_trend_baseline"
    model_version = "baseline-v1.0"
    data_provenance = "SYNTHETIC_SIMULATION"

    def generate_forecasts(
        self,
        *,
        sim_state: SimulationStateResponse,
        cells: dict[str, CellRecord],
        history: list[CellTelemetryRecord],
        horizons: list[int],
        target_cell_ids: list[str],
    ) -> list[ForecastRecord]:
        now = utc_now()
        current_by_cell = {t.cell_id: t for t in sim_state.telemetry}

        # Group recent history by cell_id for trend slope
        prev_by_cell: dict[str, CellTelemetryRecord] = {}
        for rec in history:
            if rec.tick == sim_state.tick - 1:
                prev_by_cell[rec.cell_id] = rec

        forecasts: list[ForecastRecord] = []
        cur_t_mult = max(0.25, temporal_profile_multiplier(sim_state.tick))

        for cid in sorted(target_cell_ids):
            cur = current_by_cell.get(cid)
            cell = cells.get(cid)
            if cur is None or cell is None:
                continue

            prev = prev_by_cell.get(cid)
            bg_trend = (
                (cur.background_demand_mbps - prev.background_demand_mbps)
                if prev is not None
                else 0.0
            )

            for horizon_min in horizons:
                steps_ahead = max(1, round(horizon_min / 5.0))
                future_t_mult = temporal_profile_multiplier(sim_state.tick + steps_ahead)

                projected_event = cur.event_demand_mbps * (future_t_mult / cur_t_mult)
                projected_bg = max(0.0, cur.background_demand_mbps + bg_trend * min(steps_ahead, 3) * 0.35)
                projected_traffic = round(projected_bg + projected_event, 2)

                if cur.cell_state == "FAILED":
                    projected_lat = 250.0
                elif cur.cell_state == "STANDBY":
                    projected_lat = 0.0
                else:
                    cap = max(1.0, cell.capacity_mbps)
                    ratio = projected_traffic / cap
                    projected_lat = round(
                        18.0 + 22.0 * (min(ratio, 1.8) ** 2) + max(0.0, ratio - 1.0) * 55.0,
                        2,
                    )

                target_at = sim_state.sim_time_utc + timedelta(minutes=horizon_min)

                # Quantiles P10/P90 stay None because this baseline does not compute probabilistic quantiles
                forecasts.append(
                    ForecastRecord(
                        run_id=sim_state.simulation_id,
                        event_id=sim_state.active_event_id,
                        state_version=sim_state.state_version,
                        seed=sim_state.seed,
                        cell_id=cid,
                        horizon_min=horizon_min,
                        metric="traffic_mbps",
                        unit="Mbps",
                        predicted_value=projected_traffic,
                        p10=None,
                        p50=projected_traffic,
                        p90=None,
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_at,
                    )
                )
                forecasts.append(
                    ForecastRecord(
                        run_id=sim_state.simulation_id,
                        event_id=sim_state.active_event_id,
                        state_version=sim_state.state_version,
                        seed=sim_state.seed,
                        cell_id=cid,
                        horizon_min=horizon_min,
                        metric="simulated_end_to_end_latency_ms",
                        unit="ms",
                        predicted_value=projected_lat,
                        p10=None,
                        p50=projected_lat,
                        p90=None,
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_at,
                    )
                )
        return forecasts


class RuleBasedRiskDetector:
    """Evaluates deterministic threshold-based cell risk with explicit source telemetry drivers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def assess(
        self,
        *,
        sim_state: SimulationStateResponse,
        cells: dict[str, CellRecord],
        edges: list[CellEdgeRecord],
        forecasts: list[ForecastRecord],
        target_cell_ids: list[str],
    ) -> list[CellRiskRecord]:
        now = utc_now()
        cur_by_cell = {t.cell_id: t for t in sim_state.telemetry}

        # Neighbour lookup
        neighbors: dict[str, list[str]] = {cid: [] for cid in cells}
        for e in edges:
            if e.enabled:
                neighbors.setdefault(e.source_cell_id, []).append(e.target_cell_id)
                neighbors.setdefault(e.target_cell_id, []).append(e.source_cell_id)

        # Nearest-horizon forecast lookup per cell
        fc_traffic: dict[str, float] = {}
        fc_latency: dict[str, float] = {}
        min_horizon_seen: dict[str, int] = {}
        for f in forecasts:
            if f.metric == "traffic_mbps":
                if f.cell_id not in min_horizon_seen or f.horizon_min <= min_horizon_seen[f.cell_id]:
                    min_horizon_seen[f.cell_id] = f.horizon_min
                    fc_traffic[f.cell_id] = f.predicted_value
            elif f.metric == "simulated_end_to_end_latency_ms":
                if f.cell_id not in min_horizon_seen or f.horizon_min <= min_horizon_seen[f.cell_id]:
                    fc_latency[f.cell_id] = f.predicted_value

        assessments: list[CellRiskRecord] = []
        for cid in sorted(target_cell_ids):
            cur = cur_by_cell.get(cid)
            cell = cells.get(cid)
            if cur is None or cell is None:
                continue

            pred_t = fc_traffic.get(cid, cur.demand_mbps)
            pred_lat = fc_latency.get(cid, cur.simulated_latency_ms)
            pred_util = (
                round(min(100.0, (pred_t / max(1.0, cell.capacity_mbps)) * 100.0), 2)
                if cur.cell_state == "ACTIVE"
                else 0.0
            )
            peak_util = max(cur.utilisation_pct, pred_util)
            peak_lat = max(cur.simulated_latency_ms, pred_lat)

            if cur.cell_state == "FAILED" or peak_util >= self.settings.risk_util_critical or peak_lat >= self.settings.risk_latency_critical_ms or cur.unserved_mbps > 0:
                band: RiskBand = "CRITICAL"
            elif peak_util >= self.settings.risk_util_high or peak_lat >= self.settings.risk_latency_high_ms or cur.queued_mbps > 0:
                band = "HIGH"
            elif peak_util >= self.settings.risk_util_moderate or peak_lat >= self.settings.risk_latency_moderate_ms:
                band = "MODERATE"
            else:
                band = "LOW"

            nbr_ids = neighbors.get(cid, [])
            nbr_utils = [
                cur_by_cell[nid].utilisation_pct
                for nid in nbr_ids
                if nid in cur_by_cell and cur_by_cell[nid].cell_state == "ACTIVE"
            ]
            avg_nbr_util = round(sum(nbr_utils) / max(1, len(nbr_utils)), 2) if nbr_utils else 0.0

            drivers: list[RiskDriver] = [
                RiskDriver(
                    feature="utilisation_pct",
                    value=peak_util,
                    threshold=self.settings.risk_util_high,
                    description=f"Current utilisation {cur.utilisation_pct:.1f}%, forecast {pred_util:.1f}%",
                ),
                RiskDriver(
                    feature="simulated_latency_ms",
                    value=peak_lat,
                    threshold=self.settings.risk_latency_high_ms,
                    description=f"Current latency {cur.simulated_latency_ms:.1f} ms, forecast {pred_lat:.1f} ms",
                ),
            ]
            if cur.event_demand_mbps > 0.0:
                drivers.append(
                    RiskDriver(
                        feature="event_demand_mbps",
                        value=cur.event_demand_mbps,
                        threshold=None,
                        description=f"Event uplift contributing {cur.event_demand_mbps:.1f} Mbps",
                    )
                )
            if avg_nbr_util > 0.0:
                drivers.append(
                    RiskDriver(
                        feature="neighbour_mean_utilisation_pct",
                        value=avg_nbr_util,
                        threshold=self.settings.risk_util_high,
                        description=f"Mean active neighbour utilisation is {avg_nbr_util:.1f}%",
                    )
                )
            if cid in sim_state.faults:
                drivers.append(
                    RiskDriver(
                        feature="injected_fault",
                        value=str(sim_state.faults[cid].get("fault_type")),
                        threshold=None,
                        description="Active fault injection present on cell/backhaul",
                    )
                )

            assessments.append(
                CellRiskRecord(
                    run_id=sim_state.simulation_id,
                    event_id=sim_state.active_event_id,
                    state_version=sim_state.state_version,
                    cell_id=cid,
                    risk_band=band,
                    risk_method="rule_based_threshold_v1",
                    probability=None,  # Rule-based risk band only; never invent uncalibrated probability
                    current_utilisation_pct=cur.utilisation_pct,
                    forecast_utilisation_pct=pred_util,
                    current_latency_ms=cur.simulated_latency_ms,
                    forecast_latency_ms=pred_lat,
                    drivers=drivers,
                    generated_at=now,
                )
            )
        return assessments


class PredictionService:
    """Coordinates forecast generation, rule-based risk detection, persistence, and WS broadcast."""

    def __init__(
        self,
        *,
        settings: Settings,
        network_repo: NetworkRepository,
        sim_repo: SimulationRepository,
        pred_repo: PredictionRepository,
        audit: AuditLogger,
        ws_manager: ConnectionManager,
        forecast_provider: ForecastProviderProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.network_repo = network_repo
        self.sim_repo = sim_repo
        self.pred_repo = pred_repo
        self.audit = audit
        self.ws = ws_manager
        self.forecast_provider: ForecastProviderProtocol = (
            forecast_provider or DeterministicBaselineForecastProvider()
        )
        self.risk_detector = RuleBasedRiskDetector(settings)

    def set_forecast_provider(self, provider: ForecastProviderProtocol) -> None:
        self.forecast_provider = provider

    async def generate(
        self,
        *,
        sim_state: SimulationStateResponse,
        horizons: list[int],
        cell_ids: list[str] | None = None,
    ) -> PredictionsResponse:
        cells_list = self.network_repo.get_cells(sim_state.network_id)
        edges = self.network_repo.get_edges(sim_state.network_id)
        cell_map = {c.cell_id: c for c in cells_list}
        target_ids = cell_ids if cell_ids else [c.cell_id for c in cells_list]
        target_ids = [cid for cid in target_ids if cid in cell_map]

        history = self.sim_repo.get_cell_history(sim_state.simulation_id, limit=500)
        forecasts = self.forecast_provider.generate_forecasts(
            sim_state=sim_state,
            cells=cell_map,
            history=history,
            horizons=horizons,
            target_cell_ids=target_ids,
        )
        risks = self.risk_detector.assess(
            sim_state=sim_state,
            cells=cell_map,
            edges=edges,
            forecasts=forecasts,
            target_cell_ids=target_ids,
        )
        self.pred_repo.save_forecasts_and_risks(
            sim_state.simulation_id, sim_state.state_version, forecasts, risks
        )
        self.audit.log(
            actor="system:predictor",
            action="predictions.generated",
            entity_type="simulation_run",
            entity_id=str(sim_state.simulation_id),
            state_version=sim_state.state_version,
            details={
                "method": self.forecast_provider.method_name,
                "model_version": self.forecast_provider.model_version,
                "horizons": horizons,
                "forecast_count": len(forecasts),
                "high_critical_cells": sum(
                    1 for r in risks if r.risk_band in ("HIGH", "CRITICAL")
                ),
            },
        )
        await self.ws.broadcast(
            "forecast.ready",
            {
                "simulation_id": str(sim_state.simulation_id),
                "state_version": sim_state.state_version,
                "method": self.forecast_provider.method_name,
                "forecast_count": len(forecasts),
            },
        )
        at_risk = [
            {"cell_id": r.cell_id, "risk_band": r.risk_band}
            for r in risks
            if r.risk_band in ("HIGH", "CRITICAL")
        ]
        if at_risk:
            await self.ws.broadcast(
                "risk.detected",
                {
                    "simulation_id": str(sim_state.simulation_id),
                    "state_version": sim_state.state_version,
                    "at_risk_count": len(at_risk),
                    "top_cells": at_risk[:10],
                },
            )

        return PredictionsResponse(
            simulation_id=sim_state.simulation_id,
            event_id=sim_state.active_event_id,
            state_version=sim_state.state_version,
            seed=sim_state.seed,
            method=self.forecast_provider.method_name,
            model_version=self.forecast_provider.model_version,
            data_provenance=self.forecast_provider.data_provenance,
            forecasts=forecasts,
            risk_assessments=risks,
        )
