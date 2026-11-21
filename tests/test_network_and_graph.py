from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_and_seeded_100_cells(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    h_data = health.json()
    assert h_data["status"] == "ok"
    assert h_data["network_cell_count"] == 100
    assert h_data["db_journal_mode"].lower() == "wal"

    cells_resp = client.get("/api/v1/networks/current/cells")
    assert cells_resp.status_code == 200
    cells_data = cells_resp.json()
    cells = cells_data["cells"]
    assert len(cells) == 100
    cell_ids = {c["cell_id"] for c in cells}
    assert len(cell_ids) == 100

    regions = {c["region"] for c in cells}
    assert regions == {
        "Central Business District",
        "Outer Ring Road",
        "Whitefield",
        "Electronic City",
    }

    graph_resp = client.get("/api/v1/networks/current/graph")
    assert graph_resp.status_code == 200
    graph_data = graph_resp.json()
    assert 4.0 <= graph_data["average_degree"] <= 6.0
    for edge in graph_data["edges"]:
        assert edge["source_cell_id"] in cell_ids
        assert edge["target_cell_id"] in cell_ids
        assert edge["source_cell_id"] != edge["target_cell_id"]


def test_deterministic_seed_replay(client: TestClient) -> None:
    first = client.post("/api/v1/networks/seed", json={"seed": 77, "cell_count": 100})
    assert first.status_code == 200
    cells_1 = client.get("/api/v1/networks/current/cells").json()["cells"]
    edges_1 = client.get("/api/v1/networks/current/graph").json()["edges"]

    second = client.post("/api/v1/networks/seed", json={"seed": 77, "cell_count": 100})
    assert second.status_code == 200
    cells_2 = client.get("/api/v1/networks/current/cells").json()["cells"]
    edges_2 = client.get("/api/v1/networks/current/graph").json()["edges"]

    assert first.json()["network_id"] == second.json()["network_id"]
    assert cells_1 == cells_2
    assert edges_1 == edges_2
