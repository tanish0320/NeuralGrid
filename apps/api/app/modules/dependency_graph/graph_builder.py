from __future__ import annotations

import math
import random
from uuid import UUID

import networkx as nx

from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord, EdgeType


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two synthetic coordinates."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def build_dependency_graph(
    *,
    network_id: UUID,
    cells: list[CellRecord],
    seed: int = 42,
    target_k: int = 4,
) -> tuple[nx.Graph, list[CellEdgeRecord], float]:
    """Build deterministic NetworkX dependency graph with 4-6 average neighbours per cell."""
    rng = random.Random(seed + 1009)
    graph = nx.Graph()
    for cell in cells:
        graph.add_node(cell.cell_id, region=cell.region, lat=cell.lat, lon=cell.lon)

    edges_map: dict[tuple[str, str], CellEdgeRecord] = {}
    edge_counter = 0

    def add_edge(u: CellRecord, v: CellRecord, edge_type: EdgeType) -> None:
        nonlocal edge_counter
        if u.cell_id == v.cell_id:
            return
        pair = (min(u.cell_id, v.cell_id), max(u.cell_id, v.cell_id))
        if pair in edges_map:
            return
        dist = max(0.15, haversine_km(u.lat, u.lon, v.lat, v.lon))
        weight = round(1.0 / (1.0 + dist), 4)
        max_transfer = round(min(u.capacity_mbps, v.capacity_mbps) * rng.uniform(0.32, 0.48), 2)
        edge_counter += 1
        edge = CellEdgeRecord(
            edge_id=f"EDGE-BLR-{edge_counter:04d}",
            network_id=network_id,
            source_cell_id=pair[0],
            target_cell_id=pair[1],
            edge_type=edge_type,
            weight=weight,
            max_transfer_mbps=max_transfer,
            enabled=True,
        )
        edges_map[pair] = edge
        graph.add_edge(pair[0], pair[1], edge_id=edge.edge_id, edge_type=edge_type, weight=weight)

    # Connect each cell to its nearest spatial neighbours (handover / coverage overlap)
    for cell in cells:
        ranked = sorted(
            (c for c in cells if c.cell_id != cell.cell_id),
            key=lambda other: (haversine_km(cell.lat, cell.lon, other.lat, other.lon), other.cell_id),
        )
        for idx, neighbor in enumerate(ranked[:target_k]):
            if idx < 3:
                etype: EdgeType = "handover_support"
            elif cell.region == neighbor.region:
                etype = "coverage_overlap"
            else:
                etype = "shared_backhaul"
            add_edge(cell, neighbor, etype)

    # Ensure graph connectivity across regional clusters via shared_backhaul links
    components = [sorted(list(comp)) for comp in nx.connected_components(graph)]
    cell_by_id = {c.cell_id: c for c in cells}
    if len(components) > 1:
        for i in range(len(components) - 1):
            best_pair: tuple[CellRecord, CellRecord] | None = None
            best_dist = float("inf")
            for cid_a in components[i]:
                for cid_b in components[i + 1]:
                    d = haversine_km(
                        cell_by_id[cid_a].lat,
                        cell_by_id[cid_a].lon,
                        cell_by_id[cid_b].lat,
                        cell_by_id[cid_b].lon,
                    )
                    if d < best_dist:
                        best_dist = d
                        best_pair = (cell_by_id[cid_a], cell_by_id[cid_b])
            if best_pair is not None:
                add_edge(best_pair[0], best_pair[1], "shared_backhaul")

    edges = sorted(edges_map.values(), key=lambda e: e.edge_id)
    avg_degree = round((2.0 * len(edges)) / max(1, len(cells)), 4)
    return graph, edges, avg_degree
