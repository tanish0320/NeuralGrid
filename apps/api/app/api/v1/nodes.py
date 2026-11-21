from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.app.core.security import extract_presented_token, verify_node_token
from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.twinnode import (
    HeartbeatCommandResponse,
    NodeCommandRequest,
    NodeHeartbeatRequest,
    NodeRecord,
    NodeRegisterRequest,
)

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("/register", response_model=NodeRecord)
async def register_node(
    body: NodeRegisterRequest,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> NodeRecord:
    presented = extract_presented_token(request.headers, fallback_body_token=body.token)
    if not verify_node_token(body.node_id, presented, container.settings):
        raise HTTPException(status_code=401, detail=f"Unauthorized node token for '{body.node_id}'")
    client_ip = request.client.host if request.client else "127.0.0.1"
    return await container.twinnode_controller.register_node(body, client_ip=client_ip)


@router.post("/{node_id}/heartbeat", response_model=HeartbeatCommandResponse)
async def heartbeat_node(
    node_id: str,
    body: NodeHeartbeatRequest,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> HeartbeatCommandResponse:
    presented = extract_presented_token(request.headers)
    if not verify_node_token(node_id, presented, container.settings):
        raise HTTPException(status_code=401, detail=f"Unauthorized node token for '{node_id}'")
    client_ip = request.client.host if request.client else None
    return await container.twinnode_controller.process_heartbeat(
        node_id, body, client_ip=client_ip
    )


@router.get("", response_model=list[NodeRecord])
async def list_nodes(
    container: AppContainer = Depends(get_container),
) -> list[NodeRecord]:
    return container.twinnode_repo.list_nodes()


@router.get("/{node_id}", response_model=NodeRecord)
async def get_node(
    node_id: str,
    container: AppContainer = Depends(get_container),
) -> NodeRecord:
    node = container.twinnode_repo.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' is not registered")
    return node


@router.post("/{node_id}/activate", response_model=NodeRecord)
async def activate_node(
    node_id: str,
    body: NodeCommandRequest | None = None,
    container: AppContainer = Depends(get_container),
) -> NodeRecord:
    return await container.twinnode_controller.activate_node(
        node_id, body or NodeCommandRequest()
    )


@router.post("/{node_id}/standby", response_model=NodeRecord)
async def standby_node(
    node_id: str,
    body: NodeCommandRequest | None = None,
    container: AppContainer = Depends(get_container),
) -> NodeRecord:
    return await container.twinnode_controller.standby_node(
        node_id, body or NodeCommandRequest()
    )


@router.post("/{node_id}/drain", response_model=NodeRecord)
async def drain_node(
    node_id: str,
    body: NodeCommandRequest | None = None,
    container: AppContainer = Depends(get_container),
) -> NodeRecord:
    return await container.twinnode_controller.drain_node(
        node_id, body or NodeCommandRequest()
    )


@router.post("/sweep-timeouts", response_model=dict[str, int])
async def sweep_node_timeouts(
    container: AppContainer = Depends(get_container),
) -> dict[str, int]:
    return await container.twinnode_controller.sweep_timeouts()
