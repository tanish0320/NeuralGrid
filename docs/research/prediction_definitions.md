# Prediction Definitions & Metrics Standard

**Project:** NeuralGrid v1.5  
**Author:** Tanish Renuka Suragihalli  

## 1. Metric Definitions & Units

| Metric | API Field | Unit | Horizon | Description |
|---|---|---|---|---|
| **Future Cell Traffic** | `traffic_mbps` | Mbps | 15m, 30m | Predicted aggregate demand load on cell |
| **Simulated End-to-End Latency** | `simulated_end_to_end_latency_ms` | ms | 15m, 30m | Simulated queueing + transmission delay from cell to edge gateway |
| **Cell Utilisation** | `current_utilisation_pct` | % | Current | $\frac{\text{Demand}}{\text{Capacity}} \times 100$ |

## 2. Quantile Forecast Interval Interpretation
When quantiles are computed:
- **P10:** 10th percentile conservative estimate (light traffic scenario).
- **P50:** Median expected forecast.
- **P90:** 90th percentile stress estimate (peak surge scenario).

## 3. Labeling Requirement
In the user interface, all model predictions are explicitly labelled with:
- **Method Name:** e.g. `xgboost_regressor_v1` or `deterministic_persistence_trend_baseline`
- **Model Version:** e.g. `xgb-v1.0` or `baseline-v1.0`
- **Data Provenance:** `SYNTHETIC_SIMULATION`
- Badge: `[MODEL PREDICTION]`
