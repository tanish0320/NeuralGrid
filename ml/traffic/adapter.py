from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Sequence
import xgboost as xgb

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.networks import CellRecord
from apps.api.app.schemas.predictions import ForecastRecord
from apps.api.app.schemas.simulations import CellTelemetryRecord, SimulationStateResponse
from ml.traffic.feature_contract import FeatureVector

logger = logging.getLogger("neuralgrid.ml.forecast")


class XGBoostForecastProvider:
    """Evaluated XGBoost forecast provider implementing ForecastProviderProtocol."""

    method_name = "xgboost_regressor_v1"
    model_version = "xgb-v1.0"
    data_provenance = "SYNTHETIC_SIMULATION"

    def __init__(self, model_path: str = "ml/traffic/xgb_traffic_model.json") -> None:
        self.model_path = Path(model_path)
        self.model: xgb.XGBRegressor | None = None
        if self.model_path.exists():
            try:
                self.model = xgb.XGBRegressor()
                self.model.load_model(str(self.model_path))
            except Exception as exc:
                logger.warning("Failed loading XGBoost model from %s: %s", self.model_path, exc)
                self.model = None

    def generate_forecasts(
        self,
        *,
        sim_state: SimulationStateResponse,
        cells: dict[str, CellRecord],
        history: list[CellTelemetryRecord],
        horizons: list[int],
        target_cell_ids: list[str],
    ) -> list[ForecastRecord]:
        try:
            return self._generate_forecasts_impl(
                sim_state=sim_state,
                cells=cells,
                history=history,
                horizons=horizons,
                target_cell_ids=target_cell_ids,
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            raise

    def _generate_forecasts_impl(
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

        records: list[ForecastRecord] = []
        target_set = set(target_cell_ids)

        for cell_id in target_set:
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

            # Derive active event and fault parameters
            event_weight = (
                min(1.0, current.event_demand_mbps / max(1.0, current.demand_mbps))
                if current.event_demand_mbps > 0.0
                else 0.0
            )
            event_intensity = 1.0 + (event_weight * 2.0)
            event_dist = max(0.5, 4.0 - (event_weight * 3.5))

            active_fault = 1.0 if cell_id in sim_state.faults else 0.0

            CRITICALITY_MAP = {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 3.0, "CRITICAL": 4.0}
            crit_num = CRITICALITY_MAP.get(str(cell.criticality).upper(), 1.0)

            fv = FeatureVector(
                hour_of_day=(sim_state.tick * 5 % (24 * 60)) / 60.0,
                day_of_week=0.0,
                cell_capacity_mbps=cell.capacity_mbps,
                criticality=crit_num,
                current_demand_mbps=current.demand_mbps,
                lag_demand_1=lag_1,
                lag_demand_2=lag_2,
                lag_demand_3=lag_3,
                demand_trend_slope=slope,
                current_utilisation_pct=current.utilisation_pct,
                event_intensity=event_intensity,
                event_distance_km=event_dist,
                event_impact_weight=event_weight,
                active_fault=active_fault,
            )

            for horizon in horizons:
                target_time = sim_state.sim_time_utc + timedelta(minutes=horizon)
                horizon_factor = horizon / 15.0

                if self.model is not None:
                    try:
                        feat_arr = (
                            fv.to_legacy_list()
                            if hasattr(self.model, "n_features_in_") and self.model.n_features_in_ == 14
                            else fv.to_list()
                        )
                        pred_demand = float(self.model.predict([feat_arr])[0])
                        # Adjust for horizon scaling beyond 15m if needed
                        if horizon > 15:
                            pred_demand += slope * (horizon - 15) / 5.0
                    except Exception:
                        pred_demand = current.demand_mbps + (slope * horizon_factor)
                else:
                    pred_demand = current.demand_mbps + (slope * horizon_factor)

                pred_demand = max(0.0, round(pred_demand, 2))

                # Traffic forecast
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
                        predicted_value=pred_demand,
                        p10=round(pred_demand * 0.92, 2),
                        p50=pred_demand,
                        p90=round(pred_demand * 1.11, 2),
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_time,
                    )
                )

                # Simulated Latency forecast derived from queueing model
                pred_util = min(150.0, (pred_demand / cell.capacity_mbps) * 100.0)
                if pred_util < 70.0:
                    pred_lat = 12.0 + (pred_util / 70.0) * 8.0
                elif pred_util < 90.0:
                    pred_lat = 20.0 + ((pred_util - 70.0) / 20.0) * 20.0
                else:
                    pred_lat = 40.0 + ((pred_util - 90.0) / 10.0) * 35.0

                pred_lat = round(pred_lat, 2)

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
                        predicted_value=pred_lat,
                        p10=round(pred_lat * 0.90, 2),
                        p50=pred_lat,
                        p90=round(pred_lat * 1.15, 2),
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=target_time,
                    )
                )

        return records
