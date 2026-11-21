from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.predictions import PredictionGenerateRequest, PredictionsResponse

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
    )


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
