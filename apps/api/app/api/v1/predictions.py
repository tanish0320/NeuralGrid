from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.predictions import (
    CellForecastDetailResponse,
    ForecastRecord,
    NetworkForecastSummaryResponse,
    PredictionGenerateRequest,
    PredictionsResponse,
)

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/generate", response_model=PredictionsResponse)
async def generate_predictions(
    request: PredictionGenerateRequest,
    container: AppContainer = Depends(get_container),
) -> PredictionsResponse:
    sim_state = container.sim_manager.get_state(request.simulation_id)
    return await container.prediction_service.generate(
        sim_state=sim_state,
        horizons=request.horizons,
        cell_ids=request.cell_ids,
        method=request.method,
    )


@router.get("/cells/{cell_id}", response_model=CellForecastDetailResponse)
async def get_cell_forecasts(
    cell_id: str,
    simulation_id: UUID | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> CellForecastDetailResponse:
    """Retrieve 5-horizon (5m, 15m, 30m, 60m, 120m) forecasts and uncertainty bounds for a single cell."""
    detail = container.prediction_service.get_cell_forecast_detail(cell_id, simulation_id=simulation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Cell {cell_id} not found or no telemetry available")
    return detail


@router.get("/network", response_model=NetworkForecastSummaryResponse)
async def get_network_forecasts(
    simulation_id: UUID | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> NetworkForecastSummaryResponse:
    """Retrieve network-wide multi-horizon forecast metrics and congestion counts."""
    return container.prediction_service.get_network_forecast_summary(simulation_id=simulation_id)


@router.get("/history", response_model=list[ForecastRecord])
async def get_forecast_history(
    cell_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> list[ForecastRecord]:
    """Retrieve historical forecasts across cells and horizons."""
    return container.pred_repo.get_forecast_history(cell_id=cell_id, limit=limit)


@router.get("/{simulation_id}", response_model=PredictionsResponse)
async def get_predictions(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> PredictionsResponse:
    sim_state = container.sim_manager.get_state(simulation_id)
    forecasts, risks = container.pred_repo.get_latest_for_run(simulation_id)
    provider = container.prediction_service.forecast_provider
    return PredictionsResponse(
        simulation_id=sim_state.simulation_id,
        event_id=sim_state.active_event_id,
        state_version=sim_state.state_version,
        seed=sim_state.seed,
        method=forecasts[0].method if forecasts else provider.method_name,
        model_version=forecasts[0].model_version if forecasts else provider.model_version,
        data_provenance=forecasts[0].data_provenance if forecasts else provider.data_provenance,
        forecasts=forecasts,
        risk_assessments=risks,
    )

