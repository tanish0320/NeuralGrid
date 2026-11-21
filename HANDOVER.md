# NeuralGrid v1.5 — Junaid → Tanish Handover Guide

**Prepared:** 21 November 2026  
**Scope:** Complete backend control plane, 100-cell digital twin, EventSense persistence/orchestration/URL policy, constrained planner/governance, counterfactual verification, and TwinNode distributed controller/agent are **implemented and verified**.  
**Zero overlap rule:** None of Tanish's owned files (`apps/web/`, `ml/`, `docs/research/`, or `apps/api/app/modules/event_intelligence/{service.py,providers,extraction,normalization}`) were created or modified.

---

## 1. Executive Summary & Ownership Status

| Area | Status | Owner | Notes |
|---|---|---|---|
| FastAPI control plane & SQLite WAL DB (19 tables) | **Done & verified** | Junaid | `apps/api/app/main.py`, `apps/api/app/core/database.py` |
| 100-cell synthetic network & NetworkX topology (`CELL-BLR-001`..`100`) | **Done & verified** | Junaid | Seeded automatically on startup (`seed=42`, avg degree `4–6`) |
| 5-min deterministic digital twin tick engine + faults | **Done & verified** | Junaid | Exact `demand = served + queued + unserved` invariant |
| Canonical Pydantic v2 DTOs (`apps/api/app/schemas/events.py`) | **Done & verified** | Junaid | Single source of truth for Tanish's collectors & TS types |
| Server-side URL/DNS/redirect policy (`core/url_policy.py`) | **Done & verified** | Junaid | Fail-closed empty allowlist; HTTPS-only; private/loopback IP block |
| EventSense orchestrator + repositories + seeded fallback | **Done & verified** | Junaid | Auto-loads Tanish's `service.py` when created; offline demo ready |
| Prediction baseline + rule-based risk engine + ML hook | **Done & verified** | Junaid | Uses labelled `deterministic_persistence_trend_baseline` until ML plugged in |
| Constrained planner & approval governance (`STALE`/`REJECTED`/`EXPIRED`) | **Done & verified** | Junaid | Greedy constrained allocator (`<=78%` dest fill); blocks unsafe execution |
| TwinNode controller, allowlisted tasks & Node Agent (`NODE-JUNAID` / `NODE-TANISH`) | **Done & verified** | Junaid | Token auth, `STANDBY -> ACTIVATING -> ACTIVE`, SHA-256 verification, disconnect recovery |
| Counterfactual verification & UTC audit trail | **Done & verified** | Junaid | Matched seed baseline vs intervention + separate physical task metrics |
| Windows 11 PowerShell run & smoke-test scripts | **Done & verified** | Junaid | 7 scripts under `infra/scripts/*.ps1` (AST-validated) |
| **EventSense providers/extractors/normalizers** (`service.py`, `providers/`, `extraction/`, `normalization/`) | **Ready for Tanish** | Tanish | Drop into `apps/api/app/modules/event_intelligence/` |
| **Frontend UI** (`apps/web/`) | **Ready for Tanish** | Tanish | Consume `/api/v1/*`, `/health`, and `/ws/live` |
| **ML training/evaluation & research docs** (`ml/`, `docs/research/`) | **Ready for Tanish** | Tanish | Plug into `ForecastProviderProtocol` when evaluated |

### Verified Baseline Before Handover
- **Pytest suite:** `C:\Python313\python.exe -m pytest -v` → **32 passed in 2.62s** (9 test modules covering G0–G10 & ES-05/06/07/08/11/12).
- **Live HTTP Controller + Node Agent smoke test:** `uvicorn apps.api.app.main:app` + `agents.twinnode.node_agent.run_agent` (`NODE-JUNAID`) over live loopback HTTP → registered host `MSJK`, activated worker, executed `counterfactual_batch`, verified SHA-256 checksum, returned 100 cells.
- **PowerShell AST check:** All 7 `infra/scripts/*.ps1` scripts parsed cleanly with 0 errors.

---

## 2. Quick Start: Running Junaid's Backend Right Now

1. **Create `.env` from `.env.example`:**
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` before running live EventSense crawls:
   - Replace `EVENTSENSE_ALLOWED_DOMAINS=replace-with-approved-domain-list` with your reviewed comma-separated HTTPS domains (empty/placeholder **fails closed** and blocks all crawls).
   - Set `EVENTSENSE_RSS_FEEDS` to approved HTTPS feed URLs.
   - Ensure `NEURALGRID_CORS_ORIGINS` matches your Vite dev server (default: `http://localhost:5173,http://127.0.0.1:5173`).

2. **Install Python dependencies (Python 3.11+ recommended):**
   ```powershell
   python -m pip install -r requirements-backend.txt
   # Plus Tanish's EventSense & ML libraries on controller laptop:
   python -m pip install crawl4ai==0.9.6 feedparser==6.0.14 beautifulsoup4
   crawl4ai-setup
   crawl4ai-doctor
   ```
   *(Note: `ortools` and `psutil` are optional in practice—Junaid's planner automatically falls back to `deterministic_greedy_constrained`, and `host_metrics.py` has a native Windows `ctypes` CPU/RAM fallback if `psutil` is absent.)*

3. **Start the FastAPI control plane:**
   ```powershell
   .\infra\scripts\start-controller.ps1
   ```
   Or directly:
   ```powershell
   python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000
   ```

4. **Verify immediately in browser or PowerShell:**
   - OpenAPI Swagger UI: `http://127.0.0.1:8000/docs`
   - Health check: `Invoke-RestMethod http://127.0.0.1:8000/health`  
     Expected fields: `"status": "ok"`, `"network_cell_count": 100`, `"db_journal_mode": "wal"`, `"tanish_eventsense_service_loaded": false` (flips to `true` once you add `service.py`).
   - 100 cells & graph: `http://127.0.0.1:8000/api/v1/networks/current/cells` and `http://127.0.0.1:8000/api/v1/networks/current/graph`
   - Seeded Palace Grounds fallback event: `http://127.0.0.1:8000/api/v1/events` (contains `palace-grounds-demo` with `event_origin="SEEDED_DEMO"`, `verification_status="DEMO_SCENARIO"`).

5. **Run the backend test suite anytime:**
   ```powershell
   python -m pytest -v
   ```

---

## 3. Completed Backend File Map (Do Not Rewrite)

```text
apps/api/app/
  main.py                              # FastAPI app factory, lifespan seeding, CORS, /health, /ws/live
  config.py                            # Settings(.env), fail-closed allowlist, node tokens, thresholds
  core/
    database.py                        # SQLite WAL engine, 19 tables, UTC helpers
    url_policy.py                      # HTTPS-only, allowlist, DNS/IP & redirect safety, canonicalize_url
    security.py                        # Constant-time X-Node-Token auth, SHA-256 checksums, task allowlist
    events.py                          # Immutable UTC AuditLogger
    state.py                           # AppContainer wiring repositories & services
  schemas/                             # Canonical Pydantic v2 contracts (shared with Tanish)
    events.py, networks.py, simulations.py, predictions.py, plans.py, twinnode.py, verification.py
  repositories/                        # Single-writer SQLite persistence
    networks.py, simulations.py, events.py, event_sources.py, predictions.py, plans.py, twinnode.py, verification.py
  modules/
    data_generator/network_generator.py
    dependency_graph/graph_builder.py
    event_intelligence/orchestrator.py # Imports Tanish's service.py in-process
    scenario_engine/event_impact.py
    digital_twin/engine.py
    digital_twin/forecast_risk.py      # Pluggable ForecastProviderProtocol + RuleBasedRiskDetector
    planner/optimizer.py
    governance/lifecycle.py
    verification/counterfactual.py
  api/
    websocket.py                       # /ws/live ConnectionManager
    v1/{networks,simulations,event_intelligence,events,predictions,plans,nodes,tasks,verification,audit}.py
simulation/
  seed_network.py
  tick_engine.py
agents/twinnode/
  controller/{node_manager,task_dispatcher}.py
  node_agent/{host_metrics,worker,agent_app,run_agent}.py
  tasks/{traffic_batch,scenario_evaluation,counterfactual_batch,registry}.py
infra/scripts/
  start-controller.ps1, start-agent.ps1, start-node-agent.ps1, check-lan.ps1, demo-reset.ps1, demo-smoke-test.ps1, smoke-test-twinnode.ps1
tests/                                 # 9 pytest modules (32 passing tests)
```

---

## 4. Exact Drop-In Contract #1 — EventSense Collector (`service.py`)

Create your modules inside `apps/api/app/modules/event_intelligence/`:
- `service.py` (required entry facade imported automatically by Junaid's `orchestrator.py`)
- `providers/gdelt_doc_provider.py`, `providers/rss_provider.py`, `providers/crawl4ai_provider.py`
- `extraction/schema_org_extractor.py`, `extraction/page_text_extractor.py`
- `normalization/event_normalizer.py`, `normalization/deduplication.py`

### Required Signatures in `apps/api/app/modules/event_intelligence/service.py`
Import all DTOs strictly from `apps.api.app.schemas.events` (never redefine duplicate Pydantic models):

```python
from apps.api.app.schemas.events import (
    CrawlPageResult,
    CrawlTarget,
    EventDiscoveryRequest,
    EventDiscoveryServiceResult,
    EventExtractionResult,
)

async def discover_candidates(
    request: EventDiscoveryRequest,
) -> EventDiscoveryServiceResult:
    """Call enabled GDELT DOC / RSS adapters; return ProviderCandidateResult per enabled provider."""

async def crawl_public_sources(
    sources: list[CrawlTarget],
) -> list[CrawlPageResult]:
    """Fetch only orchestrator-validated CrawlTarget records (robots check on, serial, max 5)."""

def extract_event_fields(
    page: CrawlPageResult,
) -> EventExtractionResult:
    """Extract Schema.org Event JSON-LD first, then bounded Markdown fallback. Leave unknown fields null."""
```

### Key Integration Rules Already Enforced by Junaid's Orchestrator
1. **No DB writes in `service.py`:** Return DTOs only; `orchestrator.py` handles all DB persistence, deduplication on `(run_id, canonical_url)`, and event linking.
2. **Authoritative URL safety stays server-side:** Even if your adapters pre-filter URLs, `orchestrator.py` re-runs `validate_public_https_url()` on every discovered candidate (`fetch_status="BLOCKED_POLICY"` if unsafe/unlisted), revalidates again right before creating `CrawlTarget`, and revalidates `page.final_url` via `validate_redirect_url()` (`REDIRECT_NOT_ALLOWED`) before calling `extract_event_fields()`.
3. **Never fabricate fields:** Leave unresolved `venue_name`, `start_at`, `end_at`, `latitude`, `longitude`, `attendance_low`, and `attendance_high` as `None`/missing in `EventExtractionResult.fields`. If `fields` has `event_name` (or `name`), `orchestrator.py` creates/links a `SOURCE_DISCOVERED` event and upgrades `verification_status` to `CORROBORATED` only when ≥2 distinct domains with distinct `content_hash` agree on `(name, venue_name, local_date)`.
4. **Partial provider failures:** Return one `ProviderCandidateResult` (`provider="gdelt"` or `"rss"`) for every provider in `request.enabled_providers` even on timeout/rate limit (`status="FAILED"`, `error_code="TIMEOUT"|"RATE_LIMITED"|"HTTP_ERROR"`).

---

## 5. Exact Drop-In Contract #2 — ML Forecasting (`ForecastProviderProtocol`)

Currently `apps/api/app/modules/digital_twin/forecast_risk.py` runs `DeterministicBaselineForecastProvider` (`method="deterministic_persistence_trend_baseline"`, `model_version="baseline-v1.0"`, `data_provenance="SYNTHETIC_SIMULATION"`, `p10=None`, `p90=None`).

When your XGBoost model under `ml/` is trained and evaluated against persistence:
1. Wrap inference in an adapter implementing `ForecastProviderProtocol`:
   - Attributes: `method_name: str`, `model_version: str`, `data_provenance: str`
   - Method: `generate_forecasts(self, *, sim_state: SimulationStateResponse, cells: dict[str, CellRecord], history: list[CellTelemetryRecord], horizons: list[int], target_cell_ids: list[str]) -> list[ForecastRecord]`
2. Register it on startup (or via container setup) using:
   ```python
   app.state.container.prediction_service.set_forecast_provider(your_xgb_provider)
   ```
3. Only populate `p10` / `p90` if your model actually computes calibrated quantiles; otherwise keep them `None`.

---

## 6. Exact API & WebSocket Contract for Frontend (`apps/web/`)

All REST routes sit under `/api/v1`; timestamps crossing the API boundary are ISO-8601 UTC (`...Z`).

### Screen-by-Screen Endpoint Map

- **Global Shell & Health:**
  - `GET /health` → backend status, `db_journal_mode`, `network_cell_count`, `registered_nodes`, `tanish_eventsense_service_loaded`, UTC `timestamp`
  - `WS /ws/live` → emits `{"event": "<name>", "timestamp": "...Z", "data": {...}}`  
    Events emitted: `ws.connected`, `tick.updated`, `event.created`, `event.mapped`, `event_discovery.started`, `event_discovery.provider_status`, `event_discovery.completed`, `event_source.crawl_started`, `event_source.crawl_completed`, `event_source.crawl_failed`, `event.normalised`, `event.operator_confirmed`, `forecast.ready`, `risk.detected`, `plan.pending_approval`, `plan.approved`, `plan.executed`, `node.online`, `node.heartbeat`, `node.state_changed`, `node.offline`, `task.assigned`, `task.started`, `task.completed`, `verification.completed`.

- **Command Centre & Network Twin:**
  - `POST /api/v1/networks/seed` (`{"seed": 42, "cell_count": 100}`)
  - `GET /api/v1/networks/current`
  - `GET /api/v1/networks/current/cells` → returns `{network, cells}` (100 cells with `cell_id`, `region`, `lat`, `lon`, `capacity_mbps`, `criticality`, `is_emergency`, `initial_state`, `current_state`)
  - `GET /api/v1/networks/current/graph` → returns `{network, nodes, edges, average_degree}`
  - `POST /api/v1/simulations` → creates simulation run & tick 0 telemetry (`{simulation_id, state_version, summary, telemetry, ...}`)
  - `GET /api/v1/simulations` / `GET /api/v1/simulations/{id}/state`
  - `POST /api/v1/simulations/{id}/step` | `start` | `pause` | `reset`
  - `POST /api/v1/simulations/{id}/events` (`{event_id, influence_radius_km, attendance_scenario, intensity}`)
  - `POST /api/v1/simulations/{id}/faults` (`{fault_type: "CELL_FAILURE"|"BACKHAUL_CONGESTION", cell_id, severity, active}`)

- **EventSense:**
  - `POST /api/v1/event-intelligence/discover` → returns `{run_id, status, providers, source_ids, warnings, started_at, completed_at}` (summary only; load candidate details via `/sources`)
  - `GET /api/v1/event-intelligence/runs/{run_id}`
  - `GET /api/v1/event-intelligence/sources?run_id={run_id}` (or `?event_id={event_id}`)
  - `POST /api/v1/event-intelligence/crawl` → **send `{run_id, source_ids, max_pages}` only (never send raw URLs)**
  - `GET /api/v1/events` / `GET /api/v1/events/{event_id}` / `POST /api/v1/events`
  - `POST /api/v1/events/{event_id}/confirm` → **must be called before impact!** For `palace-grounds-demo` (`SEEDED_DEMO`), pass `{"operator_id": "...", "accept_demo_assumptions": true}` (returns 422 if false).
  - `POST /api/v1/events/{event_id}/impact` (`{simulation_id, influence_radius_km, attendance_scenario}`) → returns 409 if unconfirmed, 422 if coordinates are null.

- **Prediction & Orchestration:**
  - `POST /api/v1/predictions/generate` (`{simulation_id, horizons: [15, 30], cell_ids: null}`)
  - `GET /api/v1/predictions/{simulation_id}`
  - `POST /api/v1/plans/generate` (`{simulation_id, state_version, intent, constraints}`)
  - `GET /api/v1/plans` / `GET /api/v1/plans/{plan_id}`
  - `POST /api/v1/plans/{plan_id}/approve` (`{operator_id, plan_version, state_version, notes}`)
  - `POST /api/v1/plans/{plan_id}/reject` (`{operator_id, reason}`)
  - `POST /api/v1/plans/{plan_id}/execute` (`{operator_id, expected_state_version}`) → returns 409 for unapproved, rejected, expired, or stale plans!

- **TwinNode Live Lab:**
  - `GET /api/v1/nodes` / `GET /api/v1/nodes/{node_id}` → `latest_host_telemetry` carries `label: "PHYSICAL HOST TELEMETRY — NOT CELLULAR KPI"`
  - `POST /api/v1/nodes/{node_id}/activate` | `standby` | `drain`
  - `POST /api/v1/tasks` (`{idempotency_key, task_type, origin_node_id, assigned_node_id, seed, payload}`) — returns 409 if node is `STANDBY`/`OFFLINE`
  - `GET /api/v1/tasks` / `GET /api/v1/tasks/{task_id}`

- **Verification & Governance / Audit:**
  - `POST /api/v1/verification/run` (`{simulation_id, plan_id, horizon_ticks}`)
  - `GET /api/v1/verification` / `GET /api/v1/verification/{verification_id}`
  - `GET /api/v1/audit?entity_id=...&limit=200`

---

## 7. TwinNode Two-Laptop Pairing & Demo Runbook

1. **Both laptops join the same Private Wi-Fi hotspot/router** and verify Private firewall rules with:
   ```powershell
   .\infra\scripts\check-lan.ps1 -ControllerUrl http://<TANISH_PRIVATE_IP>:8000
   ```
2. **On Tanish's laptop (Controller + Node Agent A):**
   - Start controller: `.\infra\scripts\start-controller.ps1`
   - Optionally start local Agent A:
     ```powershell
     .\infra\scripts\start-agent.ps1 -NodeId "NODE-TANISH" -ControllerUrl "http://127.0.0.1:8000" -NodeToken "dev-token-tanish" -AgentPort 8100
     ```
3. **On Junaid's laptop (Remote Node Agent B):**
   - Set `TWINNODE_CONTROLLER_URL=http://<TANISH_PRIVATE_IP>:8000` and matching `TWINNODE_NODE_TOKEN` in `.env`, then run `.\infra\scripts\start-agent.ps1`.
4. **Verify live LAN offload before starting UI rehearsal:**
   ```powershell
   .\infra\scripts\demo-smoke-test.ps1 -ControllerUrl http://127.0.0.1:8000 -TargetNodeId NODE-JUNAID
   ```
5. **Reset between demo rehearsals:**
   ```powershell
   .\infra\scripts\demo-reset.ps1 -ControllerUrl http://127.0.0.1:8000 -Seed 42
   ```

---

## 8. Recommended Start Order for Tanish

1. **Start backend & verify `/docs` + `/health`** using Section 2.
2. **Scaffold `apps/web/` (Vite + React + Tailwind + TypeScript):**
   - Generate TypeScript interfaces matching `apps/api/app/schemas/*.py`.
   - Connect `GET /api/v1/networks/current/cells` + `graph` (Cytoscape.js) and `/ws/live` (Gate G1, G2).
3. **Implement EventSense collector & UI:**
   - Run `crawl4ai-setup` / `crawl4ai-doctor` and build `apps/api/app/modules/event_intelligence/service.py` + `providers/` + `extraction/` + `normalization/` importing DTOs from `apps.api.app.schemas.events` (Gates ES-01..ES-04, G3–G5).
   - Wire EventSense screen to `/event-intelligence/discover`, `/crawl`, `/sources`, `/events/{id}/confirm`, and `/impact`, keeping the **"Use seeded demo event"** button prominently wired to `palace-grounds-demo`.
4. **Build Prediction, Orchestration, TwinNode Live Lab, Verification & Audit screens** against `/api/v1/*` and test with live `NODE-JUNAID` execution (Gates G6–G10).
5. **Train/evaluate ML model under `ml/`** (optional enhancement once UI vertical slice works) and plug into `ForecastProviderProtocol`.
