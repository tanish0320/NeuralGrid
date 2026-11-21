from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from apps.api.app.core.security import extract_presented_token, verify_node_token
from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.twinnode import (
    TaskAckRequest,
    TaskCreateRequest,
    TaskRecord,
    TaskResultSubmitRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRecord)
async def create_task(
    body: TaskCreateRequest,
    container: AppContainer = Depends(get_container),
) -> TaskRecord:
    return await container.twinnode_controller.create_and_dispatch_task(body)


@router.get("", response_model=list[TaskRecord])
async def list_tasks(
    plan_id: UUID | None = Query(default=None),
    node_id: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> list[TaskRecord]:
    return container.twinnode_repo.list_tasks(plan_id=plan_id, node_id=node_id)


@router.get("/{task_id}", response_model=TaskRecord)
async def get_task(
    task_id: UUID,
    container: AppContainer = Depends(get_container),
) -> TaskRecord:
    task = container.twinnode_repo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.post("/{task_id}/ack", response_model=TaskRecord)
async def ack_task(
    task_id: UUID,
    body: TaskAckRequest,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> TaskRecord:
    presented = extract_presented_token(request.headers)
    if not verify_node_token(body.node_id, presented, container.settings):
        raise HTTPException(status_code=401, detail=f"Unauthorized node token for '{body.node_id}'")
    return await container.twinnode_controller.ack_task(task_id, body)


@router.post("/{task_id}/result", response_model=TaskRecord)
async def submit_task_result(
    task_id: UUID,
    body: TaskResultSubmitRequest,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> TaskRecord:
    presented = extract_presented_token(request.headers)
    if not verify_node_token(body.node_id, presented, container.settings):
        raise HTTPException(status_code=401, detail=f"Unauthorized node token for '{body.node_id}'")
    return await container.twinnode_controller.submit_task_result(task_id, body)
