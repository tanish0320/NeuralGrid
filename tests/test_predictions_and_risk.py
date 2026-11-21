from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.predictions import ForecastRecord


def test_predictions_baseline_units_and_rule_based_risk(client: TestClient) -> None:
    events = client.get("/api/v1/events").json()
    demo = next(e for e in events if e["event_key"] == "palace-grounds-demo")
    client.post(
        f"/api/v1/events/{demo['event_id']}/confirm",
        json={"operator_id": "op1", "accept_demo_assumptions": True},
    )

    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    sim_id = sim["simulation_id"]

    # Baseline forecast before event
    pre_resp = client.post(
        "/api/v1/predictions/generate",
        json={"simulation_id": sim_id, "horizons": [15, 30]},
    )
    assert pre_resp.status_code == 200
    pre = pre_resp.json()
    assert pre["method"] == "deterministic_persistence_trend_baseline"
    assert pre["data_provenance"] == "SYNTHETIC_SIMULATION"
    assert len(pre["forecasts"]) == 400  # 100 cells * 2 horizons * 2 metrics
    for f in pre["forecasts"]:
        assert f["p10"] is None
        assert f["p90"] is None
        assert f["unit"] in ("Mbps", "ms")

    # Inject high-intensity event and regenerate predictions
    inj = client.post(
        f"/api/v1/simulations/{sim_id}/events",
        json={"event_id": demo["event_id"], "influence_radius_km": 3.0, "attendance_scenario": "HIGH", "intensity": 1.8},
    ).json()
    affected_cid = inj["impact"]["affected_cells"][0]["cell_id"]
    client.post(f"/api/v1/simulations/{sim_id}/step")

    post_resp = client.post(
        "/api/v1/predictions/generate",
        json={"simulation_id": sim_id, "horizons": [15, 30]},
    )
    assert post_resp.status_code == 200
    post = post_resp.json()

    pre_val = next(
        f["predicted_value"]
        for f in pre["forecasts"]
        if f["cell_id"] == affected_cid and f["horizon_min"] == 15 and f["metric"] == "traffic_mbps"
    )
    post_val = next(
        f["predicted_value"]
        for f in post["forecasts"]
        if f["cell_id"] == affected_cid and f["horizon_min"] == 15 and f["metric"] == "traffic_mbps"
    )
    assert post_val > pre_val

    risk = next(r for r in post["risk_assessments"] if r["cell_id"] == affected_cid)
    assert risk["risk_method"] == "rule_based_threshold_v1"
    assert risk["probability"] is None
    assert risk["risk_band"] in ("HIGH", "CRITICAL")
    assert any(d["feature"] == "event_demand_mbps" for d in risk["drivers"])

    stored = client.get(f"/api/v1/predictions/{sim_id}")
    assert stored.status_code == 200
    assert stored.json()["state_version"] == post["state_version"]


class _CustomMlForecastProvider:
    method_name = "xgboost_synthetic_test_stub"
    model_version = "xgb-test-0.1"
    data_provenance = "SYNTHETIC_TRAINING_EVALUATED"

    def generate_forecasts(
        self, *, sim_state, cells, history, horizons, target_cell_ids
    ) -> list[ForecastRecord]:
        now = utc_now()
        out: list[ForecastRecord] = []
        for cid in sorted(target_cell_ids)[:2]:
            for h in horizons:
                out.append(
                    ForecastRecord(
                        run_id=sim_state.simulation_id,
                        event_id=sim_state.active_event_id,
                        state_version=sim_state.state_version,
                        seed=sim_state.seed,
                        cell_id=cid,
                        horizon_min=h,
                        metric="traffic_mbps",
                        unit="Mbps",
                        predicted_value=420.0,
                        p10=380.0,
                        p50=420.0,
                        p90=465.0,
                        method=self.method_name,
                        model_version=self.model_version,
                        data_provenance=self.data_provenance,
                        generated_at=now,
                        target_at=sim_state.sim_time_utc + timedelta(minutes=h),
                    )
                )
        return out


def test_pluggable_forecast_provider_hook(client: TestClient) -> None:
    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    sim_id = sim["simulation_id"]
    client.app.state.container.prediction_service.set_forecast_provider(_CustomMlForecastProvider())  # type: ignore[attr-defined]

    resp = client.post(
        "/api/v1/predictions/generate",
        json={"simulation_id": sim_id, "horizons": [15], "cell_ids": ["CELL-BLR-001", "CELL-BLR-002"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["method"] == "xgboost_synthetic_test_stub"
    assert data["model_version"] == "xgb-test-0.1"
    assert len(data["forecasts"]) == 2
    assert data["forecasts"][0]["p10"] == 380.0
    assert data["forecasts"][0]["p90"] == 465.0
