from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.networks import (
    NetworkCellsResponse,
    NetworkGraphResponse,
    NetworkMetadata,
    NetworkSeedRequest,
)
from simulation.seed_network import seed_network_if_needed

router = APIRouter(prefix="/networks", tags=["networks"])


@router.post("/seed", response_model=NetworkMetadata)
async def seed_network(
    request: NetworkSeedRequest,
    container: AppContainer = Depends(get_container),
) -> NetworkMetadata:
    metadata = seed_network_if_needed(
        container.network_repo,
        seed=request.seed,
        cell_count=request.cell_count,
        regions=request.regions,
        force=True,
    )
    container.audit.log(
        actor="operator",
        action="network.seeded",
        entity_type="network",
        entity_id=str(metadata.network_id),
        state_version=metadata.state_version,
        details={"seed": metadata.seed, "cell_count": metadata.cell_count},
    )
    return metadata


@router.get("/current", response_model=NetworkMetadata)
async def get_current_network(
    container: AppContainer = Depends(get_container),
) -> NetworkMetadata:
    net = container.network_repo.get_current_network()
    if net is None:
        raise HTTPException(status_code=404, detail="No synthetic network has been seeded yet")
    return net


@router.get("/current/cells", response_model=NetworkCellsResponse)
async def get_current_cells(
    container: AppContainer = Depends(get_container),
) -> NetworkCellsResponse:
    net = container.network_repo.get_current_network()
    if net is None:
        raise HTTPException(status_code=404, detail="No synthetic network has been seeded yet")
    cells = container.network_repo.get_cells(net.network_id)
    return NetworkCellsResponse(network=net, cells=cells)


@router.get("/current/graph", response_model=NetworkGraphResponse)
async def get_current_graph(
    container: AppContainer = Depends(get_container),
) -> NetworkGraphResponse:
    net = container.network_repo.get_current_network()
    if net is None:
        raise HTTPException(status_code=404, detail="No synthetic network has been seeded yet")
    cells = container.network_repo.get_cells(net.network_id)
    edges = container.network_repo.get_edges(net.network_id)
    avg_degree = round((2.0 * len(edges)) / max(1, len(cells)), 4)
    return NetworkGraphResponse(
        network=net,
        nodes=cells,
        edges=edges,
        average_degree=avg_degree,
    )
