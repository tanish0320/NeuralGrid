from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    """Format a datetime (default now) as ISO-8601 UTC ending in Z."""
    target = dt if dt is not None else utc_now()
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    else:
        target = target.astimezone(timezone.utc)
    return target.isoformat().replace("+00:00", "Z")


def parse_utc(value: str | datetime) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include explicit timezone/UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS networks (
    network_id TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    cell_count INTEGER NOT NULL,
    regions_json TEXT NOT NULL,
    state_version INTEGER NOT NULL DEFAULT 1,
    is_current INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cells (
    cell_id TEXT NOT NULL,
    network_id TEXT NOT NULL,
    region TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    capacity_mbps REAL NOT NULL,
    backhaul_capacity_mbps REAL NOT NULL,
    base_load_mbps REAL NOT NULL,
    criticality TEXT NOT NULL,
    is_emergency INTEGER NOT NULL,
    initial_state TEXT NOT NULL,
    current_state TEXT NOT NULL,
    PRIMARY KEY (network_id, cell_id),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cell_edges (
    edge_id TEXT NOT NULL,
    network_id TEXT NOT NULL,
    source_cell_id TEXT NOT NULL,
    target_cell_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL,
    max_transfer_mbps REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (network_id, edge_id),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE,
    FOREIGN KEY (network_id, source_cell_id) REFERENCES cells(network_id, cell_id) ON DELETE CASCADE,
    FOREIGN KEY (network_id, target_cell_id) REFERENCES cells(network_id, cell_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    tick INTEGER NOT NULL DEFAULT 0,
    state_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    active_event_id TEXT,
    event_intensity REAL NOT NULL DEFAULT 1.0,
    attendance_scenario TEXT NOT NULL DEFAULT 'EXPECTED',
    faults_json TEXT NOT NULL DEFAULT '{}',
    applied_transfers_json TEXT NOT NULL DEFAULT '[]',
    sim_time_utc TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    state_version INTEGER NOT NULL,
    cell_id TEXT NOT NULL,
    background_demand_mbps REAL NOT NULL,
    event_demand_mbps REAL NOT NULL,
    demand_mbps REAL NOT NULL,
    served_mbps REAL NOT NULL,
    queued_mbps REAL NOT NULL,
    unserved_mbps REAL NOT NULL,
    utilisation_pct REAL NOT NULL,
    simulated_latency_ms REAL NOT NULL,
    latency_components_json TEXT NOT NULL,
    packet_loss_pct REAL NOT NULL,
    energy_units REAL NOT NULL,
    cell_state TEXT NOT NULL,
    sim_time_utc TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(run_id, tick, cell_id),
    FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_key TEXT,
    event_origin TEXT NOT NULL,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    venue_name TEXT,
    city TEXT NOT NULL,
    address TEXT,
    latitude REAL,
    longitude REAL,
    start_at TEXT,
    end_at TEXT,
    attendance_low INTEGER,
    attendance_high INTEGER,
    attendance_basis TEXT NOT NULL,
    intensity REAL NOT NULL DEFAULT 1.0,
    verification_status TEXT NOT NULL,
    status TEXT NOT NULL,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    field_provenance_json TEXT NOT NULL DEFAULT '{}',
    confirmed_by TEXT,
    confirmed_at TEXT,
    confirmation_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_discovery_runs (
    run_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    query_terms_json TEXT NOT NULL,
    provider_config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    providers_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS event_sources (
    source_id TEXT PRIMARY KEY,
    discovery_run_id TEXT NOT NULL,
    event_id TEXT,
    discovery_provider TEXT NOT NULL,
    fetch_provider TEXT,
    source_type TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    published_at TEXT,
    discovered_at TEXT NOT NULL,
    collected_at TEXT,
    fetch_status TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    content_hash TEXT,
    evidence_summary TEXT,
    extracted_fields_json TEXT NOT NULL DEFAULT '{}',
    field_provenance_json TEXT NOT NULL DEFAULT '{}',
    crawl_attempts INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    UNIQUE(discovery_run_id, canonical_url),
    FOREIGN KEY (discovery_run_id) REFERENCES event_discovery_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_impacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    simulation_id TEXT NOT NULL,
    influence_radius_km REAL NOT NULL,
    attendance_scenario TEXT NOT NULL,
    affected_cells_json TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(event_id, simulation_id)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT,
    state_version INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    cell_id TEXT NOT NULL,
    horizon_min INTEGER NOT NULL,
    metric TEXT NOT NULL,
    unit TEXT NOT NULL,
    predicted_value REAL NOT NULL,
    p10 REAL,
    p50 REAL,
    p90 REAL,
    method TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_provenance TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    target_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT,
    state_version INTEGER NOT NULL,
    cell_id TEXT NOT NULL,
    risk_band TEXT NOT NULL,
    risk_method TEXT NOT NULL,
    probability REAL,
    current_utilisation_pct REAL NOT NULL,
    forecast_utilisation_pct REAL NOT NULL,
    current_latency_ms REAL NOT NULL,
    forecast_latency_ms REAL NOT NULL,
    drivers_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_id TEXT,
    seed INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    state_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    solver_method TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    objective_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    explanation_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_actions (
    action_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    action_order INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    amount REAL NOT NULL,
    params_json TEXT NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    state_version INTEGER NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS physical_nodes (
    node_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    ip_last_seen TEXT NOT NULL,
    agent_url TEXT,
    status TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    worker_slots INTEGER NOT NULL DEFAULT 2,
    worker_active INTEGER NOT NULL DEFAULT 0,
    desired_command TEXT,
    capacity_estimate_score REAL NOT NULL DEFAULT 1.0,
    last_heartbeat TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS node_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    cpu_pct REAL NOT NULL,
    memory_pct REAL NOT NULL,
    worker_active INTEGER NOT NULL,
    worker_slots INTEGER NOT NULL,
    active_tasks INTEGER NOT NULL,
    local_rtt_ms REAL NOT NULL,
    FOREIGN KEY (node_id) REFERENCES physical_nodes(node_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    task_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    origin_node_id TEXT NOT NULL,
    assigned_node_id TEXT NOT NULL,
    plan_id TEXT,
    simulation_id TEXT,
    event_id TEXT,
    seed INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    checksum TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_runs (
    id TEXT PRIMARY KEY,
    baseline_run_id TEXT NOT NULL,
    intervention_run_id TEXT NOT NULL,
    plan_id TEXT,
    event_id TEXT,
    seed INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    state_version INTEGER,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_source_registry (
    source_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    display_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    access_method TEXT NOT NULL,
    refresh_interval_sec INTEGER NOT NULL DEFAULT 3600,
    geographic_scope TEXT NOT NULL DEFAULT 'Bengaluru',
    supported_categories_json TEXT NOT NULL DEFAULT '["CONCERT","SPORTS","FESTIVAL","EXHIBITION","TECH_CONFERENCE"]',
    last_collected_at TEXT,
    last_error TEXT,
    health_status TEXT NOT NULL DEFAULT 'HEALTHY',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_evidence (
    evidence_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_timestamp TEXT,
    evidence_type TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    source_reliability REAL NOT NULL DEFAULT 0.8,
    evidence_confidence REAL NOT NULL DEFAULT 0.8,
    raw_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_run_tick ON telemetry(run_id, tick);
CREATE INDEX IF NOT EXISTS idx_sources_run ON event_sources(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_event ON event_evidence(event_id);
CREATE INDEX IF NOT EXISTS idx_registry_platform ON event_source_registry(platform);
CREATE INDEX IF NOT EXISTS idx_forecasts_run ON forecasts(run_id, state_version);
CREATE INDEX IF NOT EXISTS idx_plans_run ON plans(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_node_status ON tasks(assigned_node_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);
"""


class Database:
    """Thread-safe SQLite (WAL) persistence manager for the NeuralGrid controller."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=10.0,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_pragmas()

    def _configure_pragmas(self) -> None:
        with self._lock:
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.execute("PRAGMA busy_timeout=5000;")

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)

    def journal_mode(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA journal_mode;").fetchone()
            return str(row[0]) if row else "unknown"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                yield self._conn
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
