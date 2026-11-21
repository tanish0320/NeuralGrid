from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

from apps.api.app.config import Settings

ALLOWED_TASK_TYPES: frozenset[str] = frozenset(
    {
        "traffic_batch",
        "scenario_evaluation",
        "counterfactual_batch",
    }
)


def extract_presented_token(
    headers: Mapping[str, str],
    fallback_body_token: str | None = None,
) -> str | None:
    """Extract TwinNode token from X-Node-Token header, Bearer Authorization, or request body."""
    for key, val in headers.items():
        lower_key = key.lower()
        if lower_key == "x-node-token" and val.strip():
            return val.strip()
    for key, val in headers.items():
        if key.lower() == "authorization" and val.lower().startswith("bearer "):
            token = val[7:].strip()
            if token:
                return token
    if fallback_body_token and fallback_body_token.strip():
        return fallback_body_token.strip()
    return None


def verify_node_token(node_id: str, presented_token: str | None, settings: Settings) -> bool:
    """Constant-time verification of per-node authentication token."""
    if not presented_token:
        return False
    expected = settings.node_tokens_map.get(node_id)
    if not expected:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), presented_token.encode("utf-8"))


def compute_canonical_checksum(payload: Any) -> str:
    """Compute canonical SHA-256 checksum over JSON-serialisable result payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
