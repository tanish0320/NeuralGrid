from __future__ import annotations

import json
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso
from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord, NetworkMetadata


class NetworkRepository:
    """SQLite persistence for synthetic 100-cell networks and dependency edges."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_network(
        self,
        network: NetworkMetadata,
        cells: list[CellRecord],
        edges: list[CellEdgeRecord],
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE networks SET is_current = 0 WHERE is_current = 1")
            conn.execute("DELETE FROM networks WHERE network_id = ?", (str(network.network_id),))
            conn.execute(
                """
                INSERT INTO networks (network_id, seed, cell_count, regions_json, state_version, is_current, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    str(network.network_id),
                    network.seed,
                    network.cell_count,
                    json.dumps(network.regions),
                    network.state_version,
                    utc_iso(network.created_at),
                ),
            )
            conn.executemany(
                """
                INSERT INTO cells (
                    cell_id, network_id, region, lat, lon, capacity_mbps,
                    backhaul_capacity_mbps, base_load_mbps, criticality,
                    is_emergency, initial_state, current_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.cell_id,
                        str(network.network_id),
                        c.region,
                        c.lat,
                        c.lon,
                        c.capacity_mbps,
                        c.backhaul_capacity_mbps,
                        c.base_load_mbps,
                        c.criticality,
                        1 if c.is_emergency else 0,
                        c.initial_state,
                        c.current_state,
                    )
                    for c in cells
                ],
            )
            conn.executemany(
                """
                INSERT INTO cell_edges (
                    edge_id, network_id, source_cell_id, target_cell_id,
                    edge_type, weight, max_transfer_mbps, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.edge_id,
                        str(network.network_id),
                        e.source_cell_id,
                        e.target_cell_id,
                        e.edge_type,
                        e.weight,
                        e.max_transfer_mbps,
                        1 if e.enabled else 0,
                    )
                    for e in edges
                ],
            )

    def _row_to_network(self, row: object) -> NetworkMetadata:
        return NetworkMetadata(
            network_id=UUID(row["network_id"]),
            seed=int(row["seed"]),
            cell_count=int(row["cell_count"]),
            regions=json.loads(row["regions_json"]),
            state_version=int(row["state_version"]),
            created_at=parse_utc(row["created_at"]),
        )

    def get_current_network(self) -> NetworkMetadata | None:
        row = self.db.fetchone(
            "SELECT * FROM networks WHERE is_current = 1 ORDER BY created_at DESC LIMIT 1"
        )
        return self._row_to_network(row) if row else None

    def get_network_by_id(self, network_id: UUID | str) -> NetworkMetadata | None:
        row = self.db.fetchone(
            "SELECT * FROM networks WHERE network_id = ?", (str(network_id),)
        )
        return self._row_to_network(row) if row else None

    def get_cells(self, network_id: UUID | str) -> list[CellRecord]:
        rows = self.db.fetchall(
            "SELECT * FROM cells WHERE network_id = ? ORDER BY cell_id ASC",
            (str(network_id),),
        )
        return [
            CellRecord(
                cell_id=r["cell_id"],
                network_id=UUID(r["network_id"]),
                region=r["region"],
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                capacity_mbps=float(r["capacity_mbps"]),
                backhaul_capacity_mbps=float(r["backhaul_capacity_mbps"]),
                base_load_mbps=float(r["base_load_mbps"]),
                criticality=r["criticality"],
                is_emergency=bool(r["is_emergency"]),
                initial_state=r["initial_state"],
                current_state=r["current_state"],
            )
            for r in rows
        ]

    def get_edges(self, network_id: UUID | str) -> list[CellEdgeRecord]:
        rows = self.db.fetchall(
            "SELECT * FROM cell_edges WHERE network_id = ? ORDER BY edge_id ASC",
            (str(network_id),),
        )
        return [
            CellEdgeRecord(
                edge_id=r["edge_id"],
                network_id=UUID(r["network_id"]),
                source_cell_id=r["source_cell_id"],
                target_cell_id=r["target_cell_id"],
                edge_type=r["edge_type"],
                weight=float(r["weight"]),
                max_transfer_mbps=float(r["max_transfer_mbps"]),
                enabled=bool(r["enabled"]),
            )
            for r in rows
        ]

    def update_cell_states(self, network_id: UUID | str, states: dict[str, str]) -> None:
        if not states:
            return
        with self.db.transaction() as conn:
            conn.executemany(
                "UPDATE cells SET current_state = ? WHERE network_id = ? AND cell_id = ?",
                [(state, str(network_id), cid) for cid, state in states.items()],
            )

    def reset_cell_states(self, network_id: UUID | str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE cells SET current_state = initial_state WHERE network_id = ?",
                (str(network_id),),
            )

    def bump_state_version(self, network_id: UUID | str) -> int:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE networks SET state_version = state_version + 1 WHERE network_id = ?",
                (str(network_id),),
            )
            row = conn.execute(
                "SELECT state_version FROM networks WHERE network_id = ?",
                (str(network_id),),
            ).fetchone()
            return int(row["state_version"]) if row else 1
