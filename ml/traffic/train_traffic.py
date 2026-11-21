from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import xgboost as xgb

from ml.traffic.feature_contract import FEATURE_COLUMNS
from ml.traffic.generate_training_data import generate_synthetic_dataset


def train_and_evaluate(
    dataset_path: str = "ml/traffic/synthetic_traffic_dataset.csv",
    model_save_path: str = "ml/traffic/xgb_traffic_model.json",
    report_save_path: str = "ml/reports/experiment_results.md",
) -> dict[str, float]:
    """Train XGBoost model on chronologically split telemetry and evaluate vs persistence."""
    data_file = Path(dataset_path)
    if not data_file.exists():
        data_file = generate_synthetic_dataset(output_path=data_file)

    rows: list[list[float]] = []
    with open(data_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for r in reader:
            if r:
                rows.append([float(x) for x in r])

    total_n = len(rows)
    split_idx = int(total_n * 0.8)

    # Chronological split strictly enforced (no random shuffle)
    train_rows = rows[:split_idx]
    test_rows = rows[split_idx:]

    num_features = len(FEATURE_COLUMNS)
    X_train = [r[:num_features] for r in train_rows]
    y_train_15 = [r[num_features] for r in train_rows]

    X_test = [r[:num_features] for r in test_rows]
    y_test_15 = [r[num_features] for r in test_rows]
    # Current demand is feature index 4 for persistence baseline
    persistence_preds = [r[4] for r in test_rows]

    # 1. Baseline Evaluation (Persistence)
    baseline_mae = sum(abs(p - actual) for p, actual in zip(persistence_preds, y_test_15)) / len(y_test_15)
    baseline_rmse = math.sqrt(sum((p - actual) ** 2 for p, actual in zip(persistence_preds, y_test_15)) / len(y_test_15))

    # 2. XGBoost Training
    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.85,
        random_state=42,
    )
    model.fit(X_train, y_train_15)

    xgb_preds = model.predict(X_test)
    xgb_mae = float(sum(abs(p - actual) for p, actual in zip(xgb_preds, y_test_15)) / len(y_test_15))
    xgb_rmse = float(math.sqrt(sum((p - actual) ** 2 for p, actual in zip(xgb_preds, y_test_15)) / len(y_test_15)))

    # Save model
    save_file = Path(model_save_path)
    save_file.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(save_file))

    # Write Experiment Report
    rep_file = Path(report_save_path)
    rep_file.parent.mkdir(parents=True, exist_ok=True)
    report_content = f"""# NeuralGrid ML Experiment Report — Traffic Forecast

**Date:** 2026-11-21  
**Target:** 15-minute future cell demand (Mbps)  
**Method:** XGBoost Regressor (`xgb.XGBRegressor`, `max_depth=4`, `n_estimators=100`, `lr=0.08`)  
**Split Method:** Strict Chronological Time-Series Split (80% Train, 20% Out-of-Time Test)  
**Sample Count:** {total_n} samples ({len(train_rows)} train, {len(test_rows)} test)  

## Evaluation Results

| Model / Baseline | MAE (Mbps) | RMSE (Mbps) | Performance vs. Baseline |
|---|---|---|---|
| **Persistence Baseline** (current demand $\to$ target) | {baseline_mae:.2f} Mbps | {baseline_rmse:.2f} Mbps | Reference Baseline |
| **XGBoost Regressor (v1.0)** | **{xgb_mae:.2f} Mbps** | **{xgb_rmse:.2f} Mbps** | **{((baseline_mae - xgb_mae) / baseline_mae) * 100:.1f}% error reduction** |

## Invariants & Epistemic Boundaries
- **Synthetic Data:** Trained on deterministic simulation telemetry with synthetic event surge footprints.
- **DoNext RAN Finding Context:** UE-side radio measurements alone do not reliably predict QoS. In NeuralGrid, cell-level aggregation combines cell capacity, backlog queueing, event distance, and multi-tick lag features.
- **Pluggability:** Wrapped in `ForecastProviderProtocol` for in-process registration in `apps/api/app/modules/digital_twin/forecast_risk.py`.
"""
    rep_file.write_text(report_content, encoding="utf-8")

    return {
        "baseline_mae": baseline_mae,
        "baseline_rmse": baseline_rmse,
        "xgb_mae": xgb_mae,
        "xgb_rmse": xgb_rmse,
    }


if __name__ == "__main__":
    res = train_and_evaluate()
    print("Training finished:", res)
