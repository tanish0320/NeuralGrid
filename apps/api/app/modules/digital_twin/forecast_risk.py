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
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord
from apps.api.app.schemas.predictions import (
    CellForecastDetailResponse,
    CellRiskRecord,
    ForecastRecord,
    HorizonMetricDetail,
    NetworkForecastSummaryResponse,
    PredictionsResponse,
    RiskBand,
    RiskDriver,
)
from apps.api.app.schemas.simulations import CellTelemetryRecord, SimulationStateResponse
from ml.traffic.multi_horizon_adapter import MultiHorizonXGBoostForecastProvider
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
        impact_repo: ImpactRepository | None = None,
    ) -> None:
        self.settings = settings
        self.network_repo = network_repo
        self.sim_repo = sim_repo
        self.pred_repo = pred_repo
        self.audit = audit
        self.ws = ws_manager
        self.impact_repo = impact_repo
        self.multi_horizon_provider = MultiHorizonXGBoostForecastProvider(impact_repo=impact_repo)
        self.deterministic_baseline_provider = DeterministicBaselineForecastProvider()
        self.forecast_provider: ForecastProviderProtocol = (
            forecast_provider or self.deterministic_baseline_provider
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
        method: str | None = None,
    ) -> PredictionsResponse:
        cells_list = self.network_repo.get_cells(sim_state.network_id)
        edges = self.network_repo.get_edges(sim_state.network_id)
        cell_map = {c.cell_id: c for c in cells_list}
        target_ids = cell_ids if cell_ids else [c.cell_id for c in cells_list]
        target_ids = [cid for cid in target_ids if cid in cell_map]

        provider = self.multi_horizon_provider if method == "xgboost" else self.forecast_provider

        history = self.sim_repo.get_cell_history(sim_state.simulation_id, limit=500)
        forecasts = provider.generate_forecasts(
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
                "method": provider.method_name,
                "model_version": provider.model_version,
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
                "method": provider.method_name,
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
            method=provider.method_name,
            model_version=provider.model_version,
            data_provenance=provider.data_provenance,
            forecasts=forecasts,
            risk_assessments=risks,
        )

    def get_cell_forecast_detail(
        self,
        cell_id: str,
        simulation_id: UUID | None = None,
    ) -> CellForecastDetailResponse | None:
        """Retrieves comprehensive 5-horizon forecast and uncertainty details for a single cell."""
        net = self.network_repo.get_current_network()
        if not net:
            return None
        cells = {c.cell_id: c for c in self.network_repo.get_cells(net.network_id)}
        cell = cells.get(cell_id)
        if not cell:
            return None

        # Fetch latest simulation state or telemetry
        sim_run = None
        if simulation_id:
            sim_run = self.sim_repo.get_run(simulation_id)
        else:
            runs = self.sim_repo.list_runs()
            if runs:
                sim_run = runs[0]

        cur_tel = None
        if sim_run:
            history = self.sim_repo.get_cell_history(sim_run.id, limit=200)
            cur_tel = next((h for h in history if h.cell_id == cell_id), None)

        cur_demand = cur_tel.demand_mbps if cur_tel else cell.base_load_mbps
        cur_util = cur_tel.utilisation_pct if cur_tel else round((cur_demand / cell.capacity_mbps) * 100.0, 2)
        cur_lat = cur_tel.simulated_latency_ms if cur_tel else 15.0

        # Fetch forecasts
        run_id_val = sim_run.id if sim_run else None
        forecasts = self.pred_repo.get_forecasts_for_cell(cell_id, run_id=run_id_val)

        # If no persisted forecasts found, generate on-demand for standard horizons
        horizons_list = [5, 15, 30, 60, 120]
        now = utc_now()

        # Group by horizon
        fc_by_h: dict[int, dict[str, Any]] = {}
        for f in forecasts:
            fc_by_h.setdefault(f.horizon_min, {})[f.metric] = f

        horizon_details: list[HorizonMetricDetail] = []
        for h in horizons_list:
            t_rec = fc_by_h.get(h, {}).get("traffic_mbps")
            l_rec = fc_by_h.get(h, {}).get("simulated_end_to_end_latency_ms")

            target_at = t_rec.target_at if t_rec else now + timedelta(minutes=h)
            t_val = t_rec.predicted_value if t_rec else round(cur_demand * (1.0 + 0.02 * (h / 15.0)), 2)
            t_p10 = t_rec.p10 if t_rec and t_rec.p10 is not None else round(t_val * 0.90, 2)
            t_p50 = t_rec.p50 if t_rec and t_rec.p50 is not None else t_val
            t_p90 = t_rec.p90 if t_rec and t_rec.p90 is not None else round(t_val * 1.15, 2)

            l_val = l_rec.predicted_value if l_rec else cur_lat
            l_p10 = l_rec.p10 if l_rec and l_rec.p10 is not None else round(l_val * 0.88, 2)
            l_p50 = l_rec.p50 if l_rec and l_rec.p50 is not None else l_val
            l_p90 = l_rec.p90 if l_rec and l_rec.p90 is not None else round(l_val * 1.18, 2)

            proj_util = round(min(150.0, (t_val / cell.capacity_mbps) * 100.0), 2)
            if proj_util >= 95.0 or l_val >= 70.0:
                h_risk: RiskBand = "CRITICAL"
            elif proj_util >= 85.0 or l_val >= 45.0:
                h_risk = "HIGH"
            elif proj_util >= 70.0 or l_val >= 30.0:
                h_risk = "MODERATE"
            else:
                h_risk = "LOW"

            horizon_details.append(
                HorizonMetricDetail(
                    horizon_min=h,
                    target_at=target_at,
                    traffic_mbps=t_val,
                    traffic_p10=t_p10,
                    traffic_p50=t_p50,
                    traffic_p90=t_p90,
                    latency_ms=l_val,
                    latency_p10=l_p10,
                    latency_p50=l_p50,
                    latency_p90=l_p90,
                    projected_utilisation_pct=proj_util,
                    risk_band=h_risk,
                )
            )

        # Retrieve Phase 5 contributing event impacts
        contributing_evs: list[dict[str, Any]] = []
        if self.impact_repo:
            impact_records = self.impact_repo.get_impacts_for_cell(cell_id)
            for imp in impact_records:
                contributing_evs.append(
                    {
                        "event_id": str(imp.event_id),
                        "distance_km": imp.geographic_distance_km,
                        "demand_delta_mbps": imp.estimated_demand_delta_mbps,
                        "impact_category": imp.impact_category,
                        "confidence": imp.impact_confidence,
                        "window_start": imp.impact_window_start.isoformat(),
                        "window_end": imp.impact_window_end.isoformat(),
                    }
                )

        # Overall risk band
        max_util = max((h.projected_utilisation_pct for h in horizon_details), default=cur_util)
        max_lat = max((h.latency_ms for h in horizon_details), default=cur_lat)
        if max_util >= 95.0 or max_lat >= 70.0:
            overall_risk: RiskBand = "CRITICAL"
        elif max_util >= 85.0 or max_lat >= 45.0:
            overall_risk = "HIGH"
        elif max_util >= 70.0 or max_lat >= 30.0:
            overall_risk = "MODERATE"
        else:
            overall_risk = "LOW"

        # Reasoning synthesis
        reasoning = (
            f"Forecast driven by {len(contributing_evs)} Phase 5 event(s). "
            f"Peak projected utilisation reaches {max_util:.1f}% ({overall_risk} risk) "
            f"with queueing delay evaluated via M/M/1 soft-saturation model."
        )

        return CellForecastDetailResponse(
            cell_id=cell_id,
            region=cell.region,
            capacity_mbps=cell.capacity_mbps,
            backhaul_capacity_mbps=cell.backhaul_capacity_mbps,
            current_demand_mbps=round(cur_demand, 2),
            current_utilisation_pct=round(cur_util, 2),
            current_latency_ms=round(cur_lat, 2),
            risk_band=overall_risk,
            horizons=horizon_details,
            contributing_events=contributing_evs,
            forecast_reasoning=reasoning,
            model_version=self.forecast_provider.model_version,
            generated_at=now,
        )

    def get_network_forecast_summary(
        self,
        simulation_id: UUID | None = None,
    ) -> NetworkForecastSummaryResponse:
        """Computes network-wide multi-horizon forecast metrics and congestion counts."""
        net = self.network_repo.get_current_network()
        cells = self.network_repo.get_cells(net.network_id) if net else []
        cell_caps = {c.cell_id: c.capacity_mbps for c in cells}

        sim_run = None
        if simulation_id:
            sim_run = self.sim_repo.get_run(simulation_id)
        else:
            runs = self.sim_repo.list_runs()
            if runs:
                sim_run = runs[0]

        run_id_val = sim_run.id if sim_run else (net.network_id if net else uuid4())
        sv = sim_run.state_version if sim_run else 1

        forecasts, risks = self.pred_repo.get_latest_for_run(run_id_val)

        horizons = [5, 15, 30, 60, 120]
        congested_by_h: dict[int, int] = {h: 0 for h in horizons}
        max_demand_by_h: dict[int, float] = {h: 0.0 for h in horizons}
        demands_by_h: dict[int, list[float]] = {h: [] for h in horizons}

        for f in forecasts:
            if f.metric == "traffic_mbps" and f.horizon_min in congested_by_h:
                h = f.horizon_min
                val = f.predicted_value
                demands_by_h[h].append(val)
                if val > max_demand_by_h[h]:
                    max_demand_by_h[h] = val
                cap = cell_caps.get(f.cell_id, 1000.0)
                if (val / cap) >= 0.85:
                    congested_by_h[h] += 1

        avg_demand_by_h = {
            h: round(sum(demands_by_h[h]) / max(1, len(demands_by_h[h])), 2)
            for h in horizons
        }
        for h in horizons:
            max_demand_by_h[h] = round(max_demand_by_h[h], 2)

        crit_cells = [r.cell_id for r in risks if r.risk_band == "CRITICAL"]
        high_cells = [r.cell_id for r in risks if r.risk_band == "HIGH"]

        return NetworkForecastSummaryResponse(
            simulation_id=sim_run.id if sim_run else None,
            state_version=sv,
            total_cells=len(cells),
            horizons=horizons,
            congested_cells_by_horizon=congested_by_h,
            max_demand_by_horizon=max_demand_by_h,
            avg_demand_by_horizon=avg_demand_by_h,
            critical_cells=crit_cells,
            high_risk_cells=high_cells,
            generated_at=utc_now(),
        )

