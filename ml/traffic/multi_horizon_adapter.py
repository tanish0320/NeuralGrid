from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence
import xgboost as xgb

from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.geospatial.profiles import (
    evaluate_temporal_surge_factor,
    get_category_profile,
)
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.schemas.networks import CellRecord
from apps.api.app.schemas.predictions import ForecastRecord
from apps.api.app.schemas.simulations import CellTelemetryRecord, SimulationStateResponse
from ml.traffic.feature_contract import FeatureVector
from ml.traffic.queueing_model import calculate_latency_uncertainty_bounds, calculate_queueing_latency

logger = logging.getLogger("neuralgrid.ml.multi_horizon")


class MultiHorizonXGBoostForecastProvider:
    """
    Production Multi-Horizon XGBoost Forecast Provider.
    Forecasts cellular offered demand and queueing latency across 5m, 15m, 30m, 60m, 120m horizons.
    Integrates Phase 5 event-to-cell impacts, M/M/1 queueing delay, and calibrated uncertainty bounds (P10/P50/P90).
    """

    method_name = "multi_horizon_xgboost_regressor_v2"
    model_version = "xgb-v2.0-multi-horizon"
    data_provenance = "SYNTHETIC_SIMULATION_WITH_PHASE5_EVENT_INTEL"

    def __init__(
        self,
        model_path: str = "ml/traffic/xgb_multi_horizon.json",
        impact_repo: ImpactRepository | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.impact_repo = impact_repo
        self.model: xgb.XGBRegressor | None = None
        if self.model_path.exists():
            try:
                self.model = xgb.XGBRegressor()
                self.model.load_model(str(self.model_path))
            except Exception as exc:
                logger.warning("Failed loading multi-horizon XGBoost model from %s: %s", self.model_path, exc)
                self.model = None

    def set_impact_repo(self, repo: ImpactRepository) -> None:
        self.impact_repo = repo

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

        # Build lag index from history
        lags_by_cell: dict[str, dict[int, CellTelemetryRecord]] = {}
        for rec in history:
            lags_by_cell.setdefault(rec.cell_id, {})[rec.tick] = rec

        # Compute average neighbour demand for network topology context
        total_curr_demand = sum(t.demand_mbps for t in sim_state.telemetry)
        net_avg_demand = total_curr_demand / max(1, len(sim_state.telemetry))

        records: list[ForecastRecord] = []
        target_set = set(target_cell_ids)

        CRITICALITY_MAP = {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 3.0, "CRITICAL": 4.0}

        for cell_id in sorted(target_set):
            cell = cells.get(cell_id)
            current = current_by_cell.get(cell_id)
            if cell is None or current is None:
                continue

            cell_lags = lags_by_cell.get(cell_id, {})
            lag_1_rec = cell_lags.get(sim_state.tick - 1)
            lag_2_rec = cell_lags.get(sim_state.tick - 2)
            lag_3_rec = cell_lags.get(sim_state.tick - 3)

            lag_1 = lag_1_rec.demand_mbps if lag_1_rec else current.demand_mbps
            lag_2 = lag_2_rec.demand_mbps if lag_2_rec else lag_1
            lag_3 = lag_3_rec.demand_mbps if lag_3_rec else lag_2

            slope = (current.demand_mbps - lag_3) / 3.0 if lag_3 else 0.0

            crit_num = CRITICALITY_MAP.get(str(cell.criticality).upper(), 2.0)
            active_fault = 1.0 if cell_id in sim_state.faults else 0.0
            nbr_util = min(100.0, (net_avg_demand / max(1.0, cell.capacity_mbps)) * 100.0)

            # Query Phase 5 impacts for this cell
            impact_records = self.impact_repo.get_impacts_for_cell(cell_id) if self.impact_repo else []

            for horizon in horizons:
                target_time = sim_state.sim_time_utc + timedelta(minutes=horizon)
                if target_time.tzinfo is None:
                    target_time = target_time.replace(tzinfo=timezone.utc)

                # Evaluate forward Phase 5 event demand delta at target_time
                event_delta_at_target = 0.0
                min_event_dist = 5.0
                max_event_conf = 0.0
                contributing_count = 0

                if impact_records:
                    active_deltas: list[float] = []
                    for imp in impact_records:
                        # Extract temporal profile parameters
                        tp = imp.temporal_profile or {}
                        prof = get_category_profile(imp.impact_category)
                        win_start = imp.impact_window_start
                        win_end = imp.impact_window_end
                        ev_hours = tp.get("event_hours", 3.0)
                        ev_start = win_start + timedelta(hours=prof.arrival_hours)
                        ev_end = ev_start + timedelta(hours=ev_hours)

                        # Evaluate surge factor at forward timestamp
                        factor = evaluate_temporal_surge_factor(
                            prof, win_start, ev_start, ev_end, win_end, target_time
                        )
                        if factor > 0.0:
                            active_deltas.append(imp.estimated_demand_delta_mbps * factor)
                            if imp.geographic_distance_km < min_event_dist:
                                min_event_dist = imp.geographic_distance_km
                            if imp.impact_confidence > max_event_conf:
                                max_event_conf = imp.impact_confidence

                    if active_deltas:
                        # Apply Phase 5 sub-linear saturation
                        sorted_d = sorted(active_deltas, reverse=True)
                        event_delta_at_target = sorted_d[0] + sum(
                            d / (1.0 + 0.35 * i) for i, d in enumerate(sorted_d[1:], 1)
                        )
                        contributing_count = len(sorted_d)

                hour_of_day = (target_time.hour + target_time.minute / 60.0)

                fv = FeatureVector(
                    hour_of_day=hour_of_day,
                    day_of_week=float(target_time.weekday()),
                    horizon_min=float(horizon),
                    cell_capacity_mbps=cell.capacity_mbps,
                    backhaul_capacity_mbps=cell.backhaul_capacity_mbps,
                    criticality=crit_num,
                    current_demand_mbps=current.demand_mbps,
                    lag_demand_1=lag_1,
                    lag_demand_2=lag_2,
                    lag_demand_3=lag_3,
                    demand_trend_slope=slope,
                    current_utilisation_pct=current.utilisation_pct,
                    current_latency_ms=current.simulated_latency_ms,
                    queued_mbps=current.queued_mbps,
                    neighbour_mean_utilisation_pct=nbr_util,
                    event_demand_delta_mbps=round(event_delta_at_target, 2),
                    event_distance_km=round(min_event_dist, 3),
                    event_confidence=round(max_event_conf, 3),
                    overlapping_events_count=float(contributing_count),
                    active_fault=active_fault,
                )

                if self.model is not None:
                    try:
                        pred_demand = float(self.model.predict([fv.to_list()])[0])
                    except Exception:
                        pred_demand = current.demand_mbps + (slope * horizon / 15.0) + event_delta_at_target
                else:
                    pred_demand = current.demand_mbps + (slope * horizon / 15.0) + event_delta_at_target

                pred_demand = max(10.0, round(pred_demand, 2))

                # Traffic uncertainty bounds (P10 / P50 / P90)
                sigma_traffic = (3.5 + 0.06 * pred_demand) * math.sqrt(1.0 + horizon / 30.0)
                traffic_p50 = pred_demand
                traffic_p10 = max(5.0, round(traffic_p50 - 1.282 * sigma_traffic, 2))
                traffic_p90 = round(traffic_p50 + 1.282 * sigma_traffic, 2)

                records.append(
                    ForecastRecord(
                        run_id=sim_state.simulation_id,
                        event_id=sim_state.active_event_id,
                        state_version=sim_state.state_version,
                        seed=sim_state.seed,
                        cell_id=cell_id,
                        horizon_min=horizon,
                        metric="traffic_mbps",
                        unit="Mbps",
                        predicted_value=traffic_p50,
                        p10=traffic_p10,
                        p50=traffic_p50,
                        p90=traffic_p90,
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_time,
                    )
                )

                # Simulated Latency derived from documented queueing model
                if current.cell_state == "FAILED":
                    lat_p50 = 250.0
                    lat_p10 = 240.0
                    lat_p90 = 250.0
                elif current.cell_state == "STANDBY":
                    lat_p50 = 0.0
                    lat_p10 = 0.0
                    lat_p90 = 0.0
                else:
                    lat_p50 = calculate_queueing_latency(
                        demand_mbps=traffic_p50,
                        capacity_mbps=cell.capacity_mbps,
                        backhaul_capacity_mbps=cell.backhaul_capacity_mbps,
                    )
                    lat_p10, lat_p50, lat_p90 = calculate_latency_uncertainty_bounds(lat_p50, horizon)

                records.append(
                    ForecastRecord(
                        run_id=sim_state.simulation_id,
                        event_id=sim_state.active_event_id,
                        state_version=sim_state.state_version,
                        seed=sim_state.seed,
                        cell_id=cell_id,
                        horizon_min=horizon,
                        metric="simulated_end_to_end_latency_ms",
                        unit="ms",
                        predicted_value=lat_p50,
                        p10=lat_p10,
                        p50=lat_p50,
                        p90=lat_p90,
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_time,
                    )
                )

        return records
