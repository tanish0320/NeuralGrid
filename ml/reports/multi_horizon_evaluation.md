# NeuralGrid Phase 6 — Multi-Horizon Forecast Model Evaluation Report

**Date:** 2026-11-24
**Model Architecture:** XGBoost Multi-Horizon Regressor (`xgb_multi_horizon.json`)
**Evaluation Methodology:** Strict Chronological Time-Series Split (80% Train, 20% Held-Out Temporal Test)
**Sample Count:** 58500 total samples (46800 train, 11700 test)

## Multi-Horizon Performance vs. Baselines

| Horizon | Persistence Baseline MAE | Trend Baseline MAE | XGBoost MAE | XGBoost RMSE | MAPE (%) | Improvement vs Persistence |
|---|---|---|---|---|---|---|
| **5 min** | 14.26 Mbps | 15.13 Mbps | **14.18 Mbps** | **18.41 Mbps** | 4.43% | **+0.5%** |
| **15 min** | 14.99 Mbps | 17.72 Mbps | **14.56 Mbps** | **18.88 Mbps** | 4.49% | **+2.9%** |
| **30 min** | 17.81 Mbps | 22.91 Mbps | **14.68 Mbps** | **19.19 Mbps** | 4.48% | **+17.6%** |
| **60 min** | 24.07 Mbps | 33.95 Mbps | **17.17 Mbps** | **22.87 Mbps** | 5.07% | **+28.7%** |
| **120 min** | 36.85 Mbps | 57.3 Mbps | **20.57 Mbps** | **27.13 Mbps** | 5.82% | **+44.2%** |

## Key Modeling Observations
- **Short Horizons (5m, 15m):** High autocorrelation and telemetry lag signals allow the model to closely track physical cellular demand with under 7% MAPE.
- **Mid Horizons (30m, 60m):** Phase 5 event surge temporal profiles become the dominant predictive driver as event arrival/departure waves build up.
- **Long Horizon (120m):** Diurnal patterns and event lifecycle windows prevent runaway trend divergence that causes catastrophic errors in naive linear extrapolation.
- **Queueing Network Model:** End-to-end simulated latency follows the Kleinrock / M/M/1 queueing delay curve with soft-saturation barrier capped at 250 ms, strictly avoiding uncalibrated multiplier assumptions.