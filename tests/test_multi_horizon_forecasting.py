from __future__ import annotations

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from apps.api.app.core.database import utc_now
from ml.traffic.queueing_model import (
    calculate_queueing_latency,
    calculate_latency_uncertainty_bounds,
)
from ml.traffic.multi_horizon_adapter import MultiHorizonXGBoostForecastProvider


def test_kleinrock_queueing_latency_model():
    """Verify queueing theory latency physics and non-linear degradation."""
    # Test 1: Zero traffic -> pure propagation delay
    lat_zero = calculate_queueing_latency(
        demand_mbps=0.0,
        capacity_mbps=1000.0,
        backhaul_capacity_mbps=2000.0,
        base_propagation_ms=10.0,
    )
    assert lat_zero == pytest.approx(10.0, abs=0.1)

    # Test 2: Moderate load (50% utilization) -> modest serialization and minimal queuing
    lat_50 = calculate_queueing_latency(
        demand_mbps=500.0,
        capacity_mbps=1000.0,
        backhaul_capacity_mbps=2000.0,
        base_propagation_ms=10.0,
    )
    assert lat_50 > 10.0
    assert lat_50 < 25.0

    # Test 3: High load (95% utilization) -> sharp non-linear knee
    lat_95 = calculate_queueing_latency(
        demand_mbps=950.0,
        capacity_mbps=1000.0,
        backhaul_capacity_mbps=2000.0,
        base_propagation_ms=10.0,
    )
    assert lat_95 > 80.0  # Noticeable jump from M/M/1 asymptote

    # Test 4: Backhaul bottleneck adds extra penalty
    lat_bh = calculate_queueing_latency(
        demand_mbps=1200.0,
        capacity_mbps=2000.0,
        backhaul_capacity_mbps=1000.0,  # 1200 > 1000 -> backhaul contention penalty
        base_propagation_ms=10.0,
    )
    lat_no_bh = calculate_queueing_latency(
        demand_mbps=1200.0,
        capacity_mbps=2000.0,
        backhaul_capacity_mbps=3000.0,  # No backhaul bottleneck
        base_propagation_ms=10.0,
    )
    assert lat_bh > lat_no_bh

    # Test 5: Severe saturation caps safely at 350 ms without division by zero or NaN
    lat_over = calculate_queueing_latency(
        demand_mbps=3500.0,
        capacity_mbps=1000.0,
        backhaul_capacity_mbps=1000.0,
        base_propagation_ms=10.0,
    )
    assert lat_over <= 350.0

    # Test 6: Uncertainty bounds monotonicity
    p10_lat, p50_lat, p90_lat = calculate_latency_uncertainty_bounds(
        central_latency_ms=45.0,
        horizon_min=30,
    )
    assert p10_lat <= p50_lat <= p90_lat


def test_multi_horizon_forecast_generation_and_uncertainty(client: TestClient):
    """Verify that predictions generate for all 5 horizons with valid P10/P50/P90."""
    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    sim_id = sim["simulation_id"]

    # Generate multi-horizon forecasts using XGBoost provider
    horizons = [5, 15, 30, 60, 120]
    cell_ids = ["CELL-BLR-001", "CELL-BLR-002", "CELL-BLR-003"]
    resp = client.post(
        "/api/v1/predictions/generate",
        json={
            "simulation_id": sim_id,
            "horizons": horizons,
            "cell_ids": cell_ids,
            "method": "xgboost",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["model_version"] == "xgb-v2.0-multi-horizon"
    assert data["method"] == "multi_horizon_xgboost_regressor_v2"
    assert data["data_provenance"] == "SYNTHETIC_SIMULATION_WITH_PHASE5_EVENT_INTEL"

    # Verify forecasts
    forecasts = data["forecasts"]
    assert len(forecasts) == len(cell_ids) * len(horizons) * 2  # 3 cells * 5 horizons * 2 metrics

    for f in forecasts:
        assert f["horizon_min"] in horizons
        assert f["metric"] in ("traffic_mbps", "simulated_end_to_end_latency_ms")
        assert f["p10"] is not None
        assert f["p50"] is not None
        assert f["p90"] is not None
        assert f["p10"] <= f["p50"] <= f["p90"], f"Ordering violated: {f}"
        if f["metric"] == "traffic_mbps":
            assert f["unit"] == "Mbps"
            assert f["predicted_value"] >= 0.0
        else:
            assert f["unit"] == "ms"
            assert 5.0 <= f["predicted_value"] <= 350.0

    # Verify risk assessments
    risks = data["risk_assessments"]
    assert len(risks) == len(cell_ids)
    for r in risks:
        assert r["cell_id"] in cell_ids
        assert r["risk_band"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        assert len(r["drivers"]) > 0


def test_prediction_api_endpoints_cell_detail_and_network_summary(client: TestClient):
    """Verify GET /predictions/cells/{cell_id}, GET /predictions/network, and GET /predictions/history."""
    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    sim_id = sim["simulation_id"]

    # 1. Generate run with XGBoost
    client.post(
        "/api/v1/predictions/generate",
        json={"simulation_id": sim_id, "horizons": [5, 15, 30, 60, 120], "method": "xgboost"},
    )

    # 2. Query cell detail
    cell_resp = client.get(f"/api/v1/predictions/cells/CELL-BLR-001?simulation_id={sim_id}")
    assert cell_resp.status_code == 200
    cell_data = cell_resp.json()
    assert cell_data["cell_id"] == "CELL-BLR-001"
    assert len(cell_data["horizons"]) == 5
    for h in cell_data["horizons"]:
        assert h["horizon_min"] in (5, 15, 30, 60, 120)
        assert h["traffic_p10"] <= h["traffic_p50"] <= h["traffic_p90"]
        assert h["latency_p10"] <= h["latency_p50"] <= h["latency_p90"]
        assert 0.0 <= h["projected_utilisation_pct"] <= 350.0

    # 3. Query network summary
    net_resp = client.get(f"/api/v1/predictions/network?simulation_id={sim_id}")
    assert net_resp.status_code == 200
    net_data = net_resp.json()
    assert net_data["total_cells"] == 100
    assert net_data["horizons"] == [5, 15, 30, 60, 120]
    assert len(net_data["avg_demand_by_horizon"]) == 5
    assert len(net_data["congested_cells_by_horizon"]) == 5

    # 4. Query history
    hist_resp = client.get("/api/v1/predictions/history?limit=5")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert len(hist) >= 1
    assert hist[0]["run_id"] == sim_id
    assert hist[0]["model_version"] == "xgb-v2.0-multi-horizon"
