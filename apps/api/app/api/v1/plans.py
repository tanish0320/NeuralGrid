from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.plans import (
    PlanApproveRequest,
    PlanExecuteRequest,
    PlanExecutionResponse,
    PlanGenerateRequest,
    PlanRecord,
    PlanRejectRequest,
)

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/generate", response_model=PlanRecord)
async def generate_plan(
    request: PlanGenerateRequest,
    container: AppContainer = Depends(get_container),
) -> PlanRecord:
    return await container.governance_service.generate_plan(request)


@router.get("", response_model=list[PlanRecord])
async def list_plans(
    simulation_id: UUID | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> list[PlanRecord]:
    return container.governance_service.list_plans(simulation_id)


@router.get("/{plan_id}", response_model=PlanRecord)
async def get_plan(
    plan_id: UUID,
    container: AppContainer = Depends(get_container),
) -> PlanRecord:
    return container.governance_service.get_plan(plan_id)


@router.post("/{plan_id}/approve", response_model=PlanRecord)
async def approve_plan(
    plan_id: UUID,
    request: PlanApproveRequest,
    container: AppContainer = Depends(get_container),
) -> PlanRecord:
    return await container.governance_service.approve_plan(plan_id, request)


@router.post("/{plan_id}/reject", response_model=PlanRecord)
async def reject_plan(
    plan_id: UUID,
    request: PlanRejectRequest,
    container: AppContainer = Depends(get_container),
) -> PlanRecord:
    return await container.governance_service.reject_plan(plan_id, request)


@router.post("/{plan_id}/execute", response_model=PlanExecutionResponse)
async def execute_plan(
    plan_id: UUID,
    request: PlanExecuteRequest,
    container: AppContainer = Depends(get_container),
) -> PlanExecutionResponse:
    return await container.governance_service.execute_plan(plan_id, request)
