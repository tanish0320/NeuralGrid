from __future__ import annotations

from apps.api.app.modules.data_generator.network_generator import generate_synthetic_network
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.schemas.networks import NetworkMetadata


def seed_network_if_needed(
    repo: NetworkRepository,
    *,
    seed: int = 42,
    cell_count: int = 100,
    regions: list[str] | None = None,
    force: bool = False,
) -> NetworkMetadata:
    """Create or recreate the deterministic 100-cell synthetic network in SQLite."""
    if not force:
        current = repo.get_current_network()
        if current is not None and current.cell_count == cell_count:
            return current

    metadata, cells, edges, _ = generate_synthetic_network(
        seed=seed,
        cell_count=cell_count,
        regions=regions,
    )
    repo.save_network(metadata, cells, edges)
    return metadata
