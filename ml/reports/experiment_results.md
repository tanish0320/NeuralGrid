# NeuralGrid ML Experiment Report — Traffic Forecast

**Date:** 2026-11-21  
**Target:** 15-minute future cell demand (Mbps)  
**Method:** XGBoost Regressor (`xgb.XGBRegressor`, `max_depth=4`, `n_estimators=100`, `lr=0.08`)  
**Split Method:** Strict Chronological Time-Series Split (80% Train, 20% Out-of-Time Test)  
**Sample Count:** 5000 samples (4000 train, 1000 test)  

## Evaluation Results

| Model / Baseline | MAE (Mbps) | RMSE (Mbps) | Performance vs. Baseline |
|---|---|---|---|
| **Persistence Baseline** (current demand $	o$ target) | 84.15 Mbps | 237.39 Mbps | Reference Baseline |
| **XGBoost Regressor (v1.0)** | **17.76 Mbps** | **31.94 Mbps** | **78.9% error reduction** |

## Invariants & Epistemic Boundaries
- **Synthetic Data:** Trained on deterministic simulation telemetry with synthetic event surge footprints.
- **DoNext RAN Finding Context:** UE-side radio measurements alone do not reliably predict QoS. In NeuralGrid, cell-level aggregation combines cell capacity, backlog queueing, event distance, and multi-tick lag features.
- **Pluggability:** Wrapped in `ForecastProviderProtocol` for in-process registration in `apps/api/app/modules/digital_twin/forecast_risk.py`.
