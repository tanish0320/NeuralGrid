from __future__ import annotations

import math
import random
import uuid
from datetime import datetime
from typing import Sequence

from apps.api.app.core.database import utc_now
from apps.api.app.modules.dependency_graph.graph_builder import build_dependency_graph
from apps.api.app.schemas.networks import (
    CellEdgeRecord,
    CellOperationalState,
    CellRecord,
    CriticalityLevel,
    NetworkMetadata,
)

# Synthetic Bengaluru regional centroids (not real operator tower locations)
REGION_CENTROIDS: dict[str, tuple[float, float]] = {
    "Central Business District": (12.9988, 77.5921),  # Centered near Palace Grounds demo venue
    "Outer Ring Road": (12.9480, 77.6900),
    "Whitefield": (12.9698, 77.7500),
    "Electronic City": (12.8452, 77.6602),
}


def generate_synthetic_network(
    seed: int = 42,
    cell_count: int = 100,
    regions: Sequence[str] | None = None,
    created_at: datetime | None = None,
) -> tuple[NetworkMetadata, list[CellRecord], list[CellEdgeRecord], float]:
    """Deterministically generate a 100-cell synthetic network and dependency graph."""
    region_list = list(regions) if regions else list(REGION_CENTROIDS.keys())
    rng = random.Random(seed)
    network_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"neuralgrid.network.{seed}.{cell_count}")
    ts = created_at or utc_now()

    cells: list[CellRecord] = []
    for idx in range(cell_count):
        cell_num = idx + 1
        cell_id = f"CELL-BLR-{cell_num:03d}"
        region = region_list[idx % len(region_list)]
        base_lat, base_lon = REGION_CENTROIDS.get(region, (12.9716, 77.5946))

        # Place CBD cells slightly tighter around Palace Grounds so 3.0 km radius hits 14-20 cells
        spread_km = 2.4 if region == "Central Business District" else 3.2
        angle = rng.uniform(0.0, 2.0 * math.pi)
        radius_km = math.sqrt(rng.uniform(0.02, 1.0)) * spread_km
        d_lat = (radius_km * math.cos(angle)) / 111.0
        d_lon = (radius_km * math.sin(angle)) / (111.0 * math.cos(math.radians(base_lat)))
        lat = round(base_lat + d_lat, 6)
        lon = round(base_lon + d_lon, 6)

        # Deterministic emergency & standby allocation
        is_emergency = (idx % 9 == 0)
        is_standby = (not is_emergency) and (idx % 10 == 4)
        initial_state: CellOperationalState = "STANDBY" if is_standby else "ACTIVE"

        if is_emergency:
            criticality: CriticalityLevel = "CRITICAL"
        elif idx % 5 == 0:
            criticality = "HIGH"
        elif idx % 2 == 0:
            criticality = "MEDIUM"
        else:
            criticality = "LOW"

        capacity_mbps = round(rng.uniform(480.0, 780.0), 2)
        backhaul_capacity_mbps = round(capacity_mbps * rng.uniform(1.25, 1.65), 2)
        base_util = rng.uniform(0.36, 0.56)
        # Dormant STANDBY capacity-booster cells carry zero baseline traffic until activated
        base_load_mbps = 0.0 if initial_state == "STANDBY" else round(capacity_mbps * base_util, 2)

        cells.append(
            CellRecord(
                cell_id=cell_id,
                network_id=network_id,
                region=region,
                lat=lat,
                lon=lon,
                capacity_mbps=capacity_mbps,
                backhaul_capacity_mbps=backhaul_capacity_mbps,
                base_load_mbps=base_load_mbps,
                criticality=criticality,
                is_emergency=is_emergency,
                initial_state=initial_state,
                current_state=initial_state,
            )
        )

    _, edges, avg_degree = build_dependency_graph(
        network_id=network_id,
        cells=cells,
        seed=seed,
    )
    metadata = NetworkMetadata(
        network_id=network_id,
        seed=seed,
        cell_count=len(cells),
        regions=region_list,
        state_version=1,
        created_at=ts,
    )
    return metadata, cells, edges, avg_degree
