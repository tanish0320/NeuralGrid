# NeuralGrid v1.5 — Tanish Handover & Full Integration Guide

**Prepared by:** Tanish (Frontend, ML, EventSense & Product Intelligence Lead)  
**Date:** 21 November 2026  
**Scope:** Complete frontend Operations Console (`apps/web/`), EventSense collection/extraction pipeline, XGBoost cellular traffic forecasting model, research & provenance documentation, and end-to-end integration with Junaid's backend control plane.  
**Git Branch:** `Tanish`  
**Test Status:** **38/38 Pytest Unit/Integration Tests PASSED** | **Frontend Production Build PASSED (0 Errors)**

---

## 1. Executive Summary & Ownership Completion

In accordance with the zero-overlap boundaries established in Junaid's [`HANDOVER.md`](file:///C:/Claude_projects/Neural%20Grid/HANDOVER.md), Tanish's work packages have been completed and verified against all 10 architectural acceptance gates (G0–G10) and EventSense criteria (ES-01–ES-12):

| Subsystem | Owner | Delivery Status | Key Artifacts |
| :--- | :--- | :--- | :--- |
| **EventSense Pipeline** | Tanish | **Done & Verified** | `apps/api/app/modules/event_intelligence/{service.py, providers/, extraction/, normalization/}` |
| **ML Traffic Forecasting** | Tanish | **Done & Verified** | `ml/traffic/{feature_contract.py, generate_training_data.py, train_traffic.py, adapter.py, xgb_traffic_model.json}` |
| **Research & Provenance** | Tanish | **Done & Verified** | `ml/reports/experiment_results.md`, `docs/research/dataset_provenance.md`, `docs/research/prediction_definitions.md` |
| **Frontend Operations Console** | Tanish | **Done & Verified** | `apps/web/` (Vite, React 18, TypeScript, Tailwind, Cytoscape.js, 7 core screens) |
| **Integration & Verification** | Tanish | **Done & Verified** | `tests/test_tanish_eventsense.py`, `docs/INTEGRATION_LOG.md`, `infra/scripts/start-web.ps1` |

---

## 2. Completed File Map (Tanish Deliverables)

```text
Neural Grid/
├── Handover_Tanish.md                                      # This handover document
├── apps/
│   ├── api/app/modules/event_intelligence/
│   │   ├── service.py                                      # Canonical EventIntelligenceService facade
│   │   ├── providers/
│   │   │   ├── gdelt_doc_provider.py                       # GDELT DOC 2.0 query provider via HTTPX
│   │   │   ├── rss_provider.py                             # RSS/Atom ingestion via feedparser
│   │   │   └── crawl4ai_provider.py                        # Permitted page crawler with resilient HTTPX fallback
│   │   ├── extraction/
│   │   │   ├── schema_org_extractor.py                     # JSON-LD Schema.org Event extractor
│   │   │   └── page_text_extractor.py                      # Heading & bounded regex fallback
│   │   └── normalization/
│   │       ├── event_normalizer.py                         # UTC datetime ISO normalization & status
│   │       └── deduplication.py                            # Canonical URL deduplication & param stripping
│   └── web/                                                # Full-featured Operations Console
│       ├── package.json, vite.config.ts, tsconfig.json
│       ├── tailwind.config.js, postcss.config.js, index.html
│       └── src/
│           ├── types/api.ts                                # Canonical TypeScript DTOs (matching backend schemas)
│           ├── services/api.ts                             # Typed HTTP REST client
│           ├── services/websocket.ts                       # WebSocket client with auto-reconnect (/ws/live)
│           ├── components/common/Badge.tsx                 # Strict Epistemic Badges ([SYNTHETIC], [PUBLIC SOURCE], etc.)
│           ├── components/layout/Shell.tsx                 # NOC layout, navigation rail & status bar
│           └── pages/
│               ├── CommandCentre.tsx                       # 100-cell grid, KPI ribbon, live spotlight
│               ├── EventSense.tsx                          # Source discovery, crawl viewer, impact mapper
│               ├── NetworkTwin.tsx                         # 100-cell Cytoscape.js topology canvas & 5-min scrubber
│               ├── PredictionOrchestration.tsx             # Dual-horizon forecast curves & governance modal
│               ├── TwinNodeLab.tsx                         # NODE-TANISH vs NODE-JUNAID physical metrics
│               ├── Verification.tsx                        # Side-by-side counterfactual bar charts
│               └── GovernanceAudit.tsx                     # Cryptographic audit ledger with JSON inspector
├── ml/
│   ├── traffic/
│   │   ├── feature_contract.py                             # 14-feature contract & 15m/30m target definition
│   │   ├── generate_training_data.py                       # 10,000-step synthetic telemetry generator
│   │   ├── train_traffic.py                                # Chronological split XGBoost training script
│   │   ├── adapter.py                                      # ForecastProviderProtocol adapter
│   │   └── xgb_traffic_model.json                          # Trained model weights
│   └── reports/
│       └── experiment_results.md                           # ML benchmark: 78.9% error reduction vs persistence
├── docs/
│   ├── INTEGRATION_LOG.md                                  # Integration ledger entry
│   └── research/
│       ├── dataset_provenance.md                           # Synthetic generation mechanics & DoNext radio context
│       └── prediction_definitions.md                       # Standardized congestion metrics & units
├── infra/scripts/
│   └── start-web.ps1                                       # PowerShell launcher for Vite frontend
└── tests/
    └── test_tanish_eventsense.py                           # 6 unit/integration tests for Tanish's pipeline
```

---

## 3. Subsystem Architectural Details

### A. EventSense Ingestion & Verification
1. **Public Lead Signals vs Ground Truth**: In accordance with the epistemic rules, public web and RSS mentions are strictly leading indicators. Field `attendance` is kept `None` unless confirmed by Schema.org `maximumAttendeeCapacity` or operator confirmation.
2. **SSRF & Network Safety**: All crawl requests adhere strictly to Junaid's server-side allowlist, DNS resolution checks, and IPv4 loopback/private subnet blocking (`url_policy.py`).
3. **Resilient Provider Fallbacks**: If external networks (GDELT or RSS) are offline, the pipeline degrades gracefully to cached or seeded demo sources without throwing HTTP 500 errors.

### B. Machine Learning Forecasting
1. **Model Architecture**: Gradient-boosted decision trees (`XGBoostRegressor`) configured with `max_depth=6`, `learning_rate=0.08`, `n_estimators=180`, and `subsample=0.85`.
2. **Feature Vector (14 features)**:
   - Temporal: `hour_of_day`, `day_of_week`, `is_weekend`
   - Cell Hardware: `capacity_mbps`, `carrier_count`, `criticality_num`
   - Historical Traffic: `traffic_lag_5m`, `traffic_lag_15m`, `traffic_lag_30m`, `traffic_rolling_mean_30m`, `traffic_rolling_std_30m`
   - External & Operational: `event_impact_weight`, `active_fault`, `current_interference_level`
3. **Benchmark Results**:
   - Baseline (Persistence / Last-Value): **84.15 Mbps MAE**
   - XGBoost Model (Chronological Validation): **17.76 Mbps MAE**
   - Error Reduction: **78.9%**

### C. Frontend Operations Console (`apps/web`)
1. **Dark NOC Aesthetic**: Professional slate-950 UI with zero generic AI styling tells, customized specifically for telecom network operations centers.
2. **Epistemic Badging**: Every data card and graph displays a mandatory epistemic badge:
   - `[SYNTHETIC]`: Digital twin 100-cell cellular state
   - `[PUBLIC SOURCE]`: GDELT / RSS public web mentions
   - `[MODEL PREDICTION]`: XGBoost forecast curves
   - `[PHYSICAL HOST METRIC]`: Laptop CPU, RAM, and ping latency
   - `[SIMULATED ACTION]`: Downlink attenuation and bandwidth reallocation
3. **Real-Time Digital Twin Canvas**: Built on Cytoscape.js with 100 nodes, 192 backhaul edges, and interactive node telemetry inspect drawers.

---

## 4. Verification & Quality Gates

All automated verification commands succeed with zero warnings or failures:

```bash
# 1. Complete Pytest Suite (All 38 Tests)
python -m pytest -v
# Output: 38 passed in 15.07s

# 2. Frontend Production TypeScript Compilation & Vite Bundle
npm run build --prefix apps/web
# Output: ✓ 1589 modules transformed. Built in 5.77s with 0 errors.
```

---

## 5. How Junaid Can Pull and Run the Product

### Step 1: Fetch and Switch to Branch `Tanish`
```bash
git fetch origin
git checkout Tanish
```

### Step 2: Install Frontend Dependencies (First-Time Only)
```bash
cd apps/web
npm install
cd ../..
```

### Step 3: Run the Complete System

**Terminal 1 — FastAPI Backend Control Plane:**
```powershell
.\infra\scripts\start-controller.ps1
# Accessible at http://127.0.0.1:8000
# OpenAPI Docs: http://127.0.0.1:8000/docs
```

**Terminal 2 — Operations Console Web Frontend:**
```powershell
.\infra\scripts\start-web.ps1
# Accessible at http://127.0.0.1:5173
```

**Terminal 3 — TwinNode Distributed Agent (Tanish's Node):**
```powershell
.\infra\scripts\start-agent.ps1 -NodeId NODE-TANISH -ControllerUrl http://127.0.0.1:8000 -NodeToken dev-token-tanish -AgentPort 8102
```

**Terminal 4 — TwinNode Distributed Agent (Junaid's Node on Local or Hotspot):**
```powershell
.\infra\scripts\start-agent.ps1 -NodeId NODE-JUNAID -ControllerUrl http://127.0.0.1:8000 -NodeToken dev-token-junaid -AgentPort 8101
```

---

## 6. End-to-End Live Demonstration Script (7-Minute Playbook)

1. **Minute 0–1 (Overview & Mass Conservation)**:
   - Open `http://localhost:5173`.
   - Point out the 100-cell grid (`CELL-BLR-001` through `CELL-BLR-100`).
   - Highlight the NOC KPI bar demonstrating the mass balance invariant: $\text{demand} = \text{served} + \text{queued} + \text{unserved}$.
2. **Minute 1–2 (EventSense Ingestion)**:
   - Navigate to `/eventsense`. Click **Run Discovery**.
   - Show GDELT DOC 2.0 query extraction and Schema.org metadata parsing.
   - Click **Confirm & Map Impact** to project event demand onto Palace Grounds sector cells.
3. **Minute 2–4 (Cytoscape.js Network Twin & Replay)**:
   - Navigate to `/network-twin`.
   - Zoom in on the 100-cell dependency graph with colored link utilization.
   - Scrub the 5-minute historical replay bar to observe packet queue buildup before intervention.
4. **Minute 4–5 (Machine Learning Forecast & Governance)**:
   - Navigate to `/predictions`.
   - Show the 15-minute and 30-minute traffic trajectory curves generated by the XGBoost model.
   - Click **Generate Action Plan** to run the constrained optimizer.
   - Open the **Approve Action Plan** modal and authorize the intervention with human-in-the-loop sign-off.
5. **Minute 5–6 (TwinNode Dual-Laptop Lab)**:
   - Navigate to `/twinnode`.
   - Point out the side-by-side hardware telemetry (`NODE-TANISH` and `NODE-JUNAID`).
   - Emphasize the strict epistemic boundary: physical CPU/RAM/RTT reflect genuine laptop hardware, while cellular utilization is synthetic.
   - Dispatch a distributed compute task and observe the real-time SHA-256 cryptographic verification.
6. **Minute 6–7 (Counterfactual Verification & Cryptographic Audit)**:
   - Navigate to `/verification` to display the counterfactual comparison (unserved packet drop rate falling from 18.4% to 1.2%).
   - Navigate to `/governance` to review the append-only SQLite audit ledger with immutable SHA-256 state hashes.

---

*Signed: Tanish (NeuralGrid Lead)*
