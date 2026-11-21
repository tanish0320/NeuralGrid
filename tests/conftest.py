from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app


def make_mock_dns_resolver():
    mapping = {
        "approved.example": ["93.184.216.34"],
        "sub.approved.example": ["93.184.216.34"],
        "events.example.org": ["93.184.216.35"],
        "other-news.example.org": ["93.184.216.36"],
        "evil.example": ["93.184.216.99"],
        "rebind.approved.example": ["127.0.0.1"],
        "private.approved.example": ["10.20.30.40"],
        "linklocal.approved.example": ["169.254.169.254"],
        "ipv6mapped.approved.example": ["::ffff:127.0.0.1"],
    }

    def _resolve(host: str) -> list[str]:
        if host in mapping:
            return mapping[host]
        raise OSError(f"Unresolved test host: {host}")

    return _resolve


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    db_file = tmp_path / "neuralgrid_test.db"
    return Settings(
        neuralgrid_db_path=str(db_file),
        neuralgrid_env="test",
        eventsense_allowed_domains="approved.example,events.example.org,other-news.example.org",
        twinnode_node_tokens='{"NODE-TANISH":"test-token-tanish","NODE-JUNAID":"test-token-junaid"}',
        twinnode_heartbeat_timeout_seconds=5.0,
        twinnode_task_lease_seconds=15.0,
    )


@pytest.fixture()
def client(test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(
        settings=test_settings,
        dns_resolver=make_mock_dns_resolver(),
    )
    with TestClient(app) as tc:
        yield tc
