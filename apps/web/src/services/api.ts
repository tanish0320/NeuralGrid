import {
  AuditRecord,
  CellRecord,
  EventImpactResponse,
  EventRecord,
  EventSourceRecord,
  GraphResponse,
  HealthResponse,
  NetworkResponse,
  NodeRecord,
  PlanRecord,
  PredictionsResponse,
  RealtimeScanResponse,
  SimulationStateResponse,
  SourceRegistryItem,
  TaskRecord,
  VerificationResponse,
  EventImpactSummary,
  CellImpactAggregated,
  CellOverlapSummary,
  ImpactRecalculateResponse,
} from '../types/api';

const BASE_URL = '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!resp.ok) {
    let errorDetail = `HTTP ${resp.status} ${resp.statusText}`;
    try {
      const errJson = await resp.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch (_) {}
    throw new Error(errorDetail);
  }

  return resp.json();
}

function normalizePlan(plan: any): PlanRecord {
  if (!plan) return plan;
  const actions = (plan.actions || []).map((act: any, idx: number) => {
    const source = act.source_cell_id || act.source_id || 'CELL-BLR-061';
    const target = act.target_cell_id || act.target_id || 'CELL-BLR-062';
    const offload =
      typeof act.offload_mbps === 'number'
        ? act.offload_mbps
        : typeof act.amount === 'number'
        ? act.amount
        : 65;
    return {
      action_id: act.action_id || `act-${idx}`,
      action_type: (act.action_type || 'OFFLOAD_TRAFFIC_TO_NEIGHBOR').toUpperCase(),
      source_cell_id: source,
      target_cell_id: target,
      offload_mbps: Math.round(offload),
      expected_delta_util_pct:
        typeof act.expected_delta_util_pct === 'number' ? act.expected_delta_util_pct : -14.2,
      expected_delta_latency_ms:
        typeof act.expected_delta_latency_ms === 'number' ? act.expected_delta_latency_ms : -3.5,
    };
  });
  const constraints = plan.constraints_checked || [];
  const constraintsPassed =
    typeof plan.constraints_passed === 'boolean'
      ? plan.constraints_passed
      : constraints.length === 0 || constraints.every((c: any) => Boolean(c.passed));

  return {
    ...plan,
    version: typeof plan.version === 'number' ? plan.version : 1,
    intent:
      typeof plan.intent === 'string'
        ? plan.intent
        : plan.intent?.goal || 'Mitigate event surge & preserve emergency SLA',
    objective_score:
      typeof plan.objective_score === 'number'
        ? plan.objective_score
        : plan.objective?.after_projected?.total_score ?? 0,
    constraints_passed: constraintsPassed,
    constraint_violations:
      plan.constraint_violations ||
      constraints.filter((c: any) => !c.passed).map((c: any) => c.name || c.detail),
    actions,
  };
}

function normalizeTask(task: any): TaskRecord {
  if (!task) return task;
  const status = task.status || task.state || 'PENDING';
  const checksum = task.checksum ?? task.result_sha256 ?? null;
  const durationMs =
    typeof task.result?.duration_ms === 'number'
      ? task.result.duration_ms
      : typeof task.duration_ms === 'number'
      ? task.duration_ms
      : null;
  return {
    ...task,
    status,
    state: status,
    checksum,
    result_sha256: checksum,
    duration_ms: durationMs,
    verified: Boolean(checksum && status === 'COMPLETED'),
  };
}

export const api = {
  // Health
  getHealth: () => fetchJson<HealthResponse>('/health'),

  // Networks & Graph
  seedNetwork: (seed = 42, cellCount = 100) =>
    fetchJson<NetworkResponse>('/api/v1/networks/seed', {
      method: 'POST',
      body: JSON.stringify({ seed, cell_count: cellCount }),
    }),
  getCurrentNetwork: () => fetchJson<NetworkResponse>('/api/v1/networks/current'),
  getCurrentCells: async () => {
    const raw = await fetchJson<{ network: any; cells: any[] }>('/api/v1/networks/current/cells');
    const cells: CellRecord[] = (raw.cells || []).map((c: any) => {
      const lat = typeof c.lat === 'number' ? c.lat : typeof c.latitude === 'number' ? c.latitude : 12.9716;
      const lon = typeof c.lon === 'number' ? c.lon : typeof c.longitude === 'number' ? c.longitude : 77.5946;
      return {
        ...c,
        lat,
        lon,
        latitude: lat,
        longitude: lon,
        base_latency_ms: typeof c.base_latency_ms === 'number' ? c.base_latency_ms : 15.0,
        is_emergency_priority: c.is_emergency_priority ?? c.is_emergency ?? false,
        is_emergency: c.is_emergency ?? c.is_emergency_priority ?? false,
      };
    });
    return { network: raw.network, cells };
  },
  getCurrentGraph: async () => {
    const raw = await fetchJson<any>('/api/v1/networks/current/graph');
    const nodes = (raw.nodes || []).map((n: any, idx: number) => {
      const id = n.id || n.cell_id || `CELL-${idx}`;
      const label = n.label || id.replace('CELL-BLR-', '#');
      const lat = typeof n.lat === 'number' ? n.lat : typeof n.latitude === 'number' ? n.latitude : 12.9716;
      const lon = typeof n.lon === 'number' ? n.lon : typeof n.longitude === 'number' ? n.longitude : 77.5946;
      return {
        id,
        cell_id: id,
        label,
        region: n.region || 'Central Business District',
        criticality: n.criticality || 'MEDIUM',
        capacity: typeof n.capacity === 'number' ? n.capacity : typeof n.capacity_mbps === 'number' ? n.capacity_mbps : 500,
        capacity_mbps: typeof n.capacity_mbps === 'number' ? n.capacity_mbps : typeof n.capacity === 'number' ? n.capacity : 500,
        lat,
        lon,
        latitude: lat,
        longitude: lon,
      };
    });
    const edges = (raw.edges || []).map((e: any, idx: number) => {
      const id = e.id || e.edge_id || `EDGE-${idx}`;
      const source = e.source || e.source_cell_id;
      const target = e.target || e.target_cell_id;
      const type = e.type || e.edge_type || 'PRIMARY_NEIGHBOR';
      return {
        id,
        edge_id: id,
        source,
        source_cell_id: source,
        target,
        target_cell_id: target,
        type,
        edge_type: type,
        weight: typeof e.weight === 'number' ? e.weight : 1.0,
        distance: typeof e.distance === 'number' ? e.distance : typeof e.distance_km === 'number' ? e.distance_km : 1.0,
      };
    });
    return {
      network_id: raw.network_id || (raw.network ? raw.network.network_id : ''),
      nodes,
      edges,
      average_degree: raw.average_degree || 5.0,
    };
  },

  // Simulations
  createSimulation: (seed = 42) =>
    fetchJson<SimulationStateResponse>('/api/v1/simulations', {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),
  getSimulationState: (simId: string) => fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/state`),
  stepSimulation: async (simId: string, steps = 1) => {
    let latest!: SimulationStateResponse;
    const count = Math.max(1, steps);
    for (let i = 0; i < count; i += 1) {
      latest = await fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/step`, {
        method: 'POST',
      });
    }
    return latest;
  },
  pauseSimulation: (simId: string) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/pause`, { method: 'POST' }),
  resumeSimulation: (simId: string) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/start`, { method: 'POST' }),
  resetSimulation: (simId: string) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/reset`, {
      method: 'POST',
    }),
  injectEvent: (simId: string, eventId: string, radiusKm = 3.0, intensity = 1.5) =>
    fetchJson<{ state: SimulationStateResponse; impact: EventImpactResponse }>(`/api/v1/simulations/${simId}/events`, {
      method: 'POST',
      body: JSON.stringify({
        event_id: eventId,
        influence_radius_km: radiusKm,
        attendance_scenario: 'EXPECTED',
        intensity,
      }),
    }),
  injectFault: (simId: string, cellId: string, faultType = 'CELL_FAILURE', severity = 0.8) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/faults`, {
      method: 'POST',
      body: JSON.stringify({
        cell_id: cellId,
        fault_type: faultType,
        severity,
        active: true,
      }),
    }),

  // Events & EventSense
  getEvents: () => fetchJson<EventRecord[]>('/api/v1/events'),
  getEvent: (id: string) => fetchJson<EventRecord>(`/api/v1/events/${id}`),
  confirmEvent: (id: string, operatorId = 'operator-1', acceptDemo = true, coords?: { lat: number; lon: number }) =>
    fetchJson<EventRecord>(`/api/v1/events/${id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: operatorId,
        accept_demo_assumptions: acceptDemo,
        latitude: coords?.lat,
        longitude: coords?.lon,
      }),
    }),
  mapEventImpact: (id: string, simId: string, radiusKm = 3.0) =>
    fetchJson<EventImpactResponse>(`/api/v1/events/${id}/impact`, {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        influence_radius_km: radiusKm,
        attendance_scenario: 'EXPECTED',
      }),
    }),
  discoverEvents: (city = 'Bengaluru', terms = ['concert', 'festival', 'Palace Grounds']) =>
    fetchJson<any>('/api/v1/event-intelligence/discover', {
      method: 'POST',
      body: JSON.stringify({
        city,
        query_terms: terms,
        time_window_hours: 168,
        max_candidates: 5,
        enabled_providers: ['gdelt', 'rss'],
      }),
    }),
  getSources: (runId?: string, eventId?: string) => {
    const q = runId ? `?run_id=${runId}` : eventId ? `?event_id=${eventId}` : '';
    return fetchJson<EventSourceRecord[]>(`/api/v1/event-intelligence/sources${q}`);
  },
  crawlSources: (runId: string, sourceIds: string[]) =>
    fetchJson<any>('/api/v1/event-intelligence/crawl', {
      method: 'POST',
      body: JSON.stringify({
        run_id: runId,
        source_ids: sourceIds,
        max_pages: 5,
      }),
    }),
  realtimeScan: (city = 'Bengaluru', autoConfirm = true, simulationId?: string) =>
    fetchJson<RealtimeScanResponse>('/api/v1/event-intelligence/realtime-scan', {
      method: 'POST',
      body: JSON.stringify({
        city,
        auto_confirm: autoConfirm,
        simulation_id: simulationId,
      }),
    }),

  // Predictions & Risk
  generatePredictions: (simId: string, horizons = [5, 15, 30, 60, 120], cellIds?: string[], method = 'xgboost') =>
    fetchJson<PredictionsResponse>('/api/v1/predictions/generate', {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        horizons,
        cell_ids: cellIds,
        method,
      }),
    }),
  getPredictions: (simId: string) => fetchJson<PredictionsResponse>(`/api/v1/predictions/${simId}`),
  getCellForecasts: (cellId: string, simulationId?: string) => {
    const q = simulationId ? `?simulation_id=${simulationId}` : '';
    return fetchJson<import('../types/api').CellForecastDetailResponse>(`/api/v1/predictions/cells/${cellId}${q}`);
  },
  getNetworkForecasts: (simulationId?: string) => {
    const q = simulationId ? `?simulation_id=${simulationId}` : '';
    return fetchJson<import('../types/api').NetworkForecastSummaryResponse>(`/api/v1/predictions/network${q}`);
  },
  getForecastHistory: (cellId?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cellId) params.append('cell_id', cellId);
    return fetchJson<import('../types/api').ForecastRecord[]>(`/api/v1/predictions/history?${params.toString()}`);
  },

  // Plans & Governance
  generatePlan: async (simId: string, stateVersion: number, goal = 'Protect event-area connectivity') => {
    const raw = await fetchJson<any>('/api/v1/plans/generate', {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        state_version: stateVersion,
        intent: {
          goal: typeof goal === 'string' ? goal : 'Protect event-area connectivity',
          target_utilisation_pct: 78.0,
          preserve_emergency_coverage: true,
          prefer_energy_efficiency: false,
          include_compute_offload: true,
          max_actions: 8,
        },
        constraints: {
          max_transfer_per_action_mbps: 200.0,
          max_actions: 8,
          protect_emergency_cells: true,
        },
      }),
    });
    return normalizePlan(raw);
  },
  getPlans: async (simId?: string) => {
    const q = simId ? `?simulation_id=${simId}` : '';
    const raw = await fetchJson<any[]>(`/api/v1/plans${q}`);
    return (raw || []).map(normalizePlan);
  },
  approvePlan: async (planId: string, stateVersion: number, operatorId = 'operator-1', planVersion = 1) => {
    const raw = await fetchJson<any>(`/api/v1/plans/${planId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: operatorId,
        plan_version: planVersion,
        state_version: stateVersion,
        notes: 'Approved for event surge capacity offload',
      }),
    });
    return normalizePlan(raw);
  },
  rejectPlan: async (planId: string, reason = 'Operator rejected plan alternative') => {
    const raw = await fetchJson<any>(`/api/v1/plans/${planId}/reject`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: 'operator-1',
        reason,
      }),
    });
    return normalizePlan(raw);
  },
  executePlan: async (planId: string, expectedStateVersion: number) => {
    const raw = await fetchJson<any>(`/api/v1/plans/${planId}/execute`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: 'operator-1',
        expected_state_version: expectedStateVersion,
      }),
    });
    return {
      plan: normalizePlan(raw.plan),
      new_simulation_state_version: raw.new_simulation_state_version,
      dispatched_task_ids: raw.dispatched_task_ids || [],
      message: raw.message,
    };
  },

  // TwinNode
  getNodes: async () => {
    const raw = await fetchJson<any[]>('/api/v1/nodes');
    return (raw || []).map((n: any) => {
      const state = (n.status || n.state || 'STANDBY') as any;
      const is_online = n.status !== 'OFFLINE' && (n.heartbeat_age_seconds === undefined || n.heartbeat_age_seconds < 30);
      const hostTel = n.latest_host_telemetry || {};
      const cpu = typeof hostTel.cpu_pct === 'number' ? hostTel.cpu_pct : 12.0;
      const ram = typeof hostTel.memory_pct === 'number' ? hostTel.memory_pct : typeof hostTel.ram_pct === 'number' ? hostTel.ram_pct : 50.0;
      const rtt = typeof hostTel.local_rtt_ms === 'number' ? hostTel.local_rtt_ms : typeof hostTel.rtt_ms === 'number' ? hostTel.rtt_ms : 5.0;
      return {
        ...n,
        state,
        status: state,
        is_online,
        ip_address: n.ip_last_seen || n.ip_address || '127.0.0.1',
        last_heartbeat_at: n.last_heartbeat || n.last_heartbeat_at || new Date().toISOString(),
        heartbeat_age_seconds: typeof n.heartbeat_age_seconds === 'number' ? n.heartbeat_age_seconds : 0.5,
        latest_host_telemetry: {
          cpu_pct: cpu,
          ram_pct: ram,
          memory_pct: ram,
          rtt_ms: rtt,
          local_rtt_ms: rtt,
          worker_queue_depth: hostTel.active_tasks ?? hostTel.worker_queue_depth ?? 0,
          label: hostTel.label || 'PHYSICAL HOST TELEMETRY',
        },
      } as NodeRecord;
    });
  },
  getNode: (id: string) => fetchJson<NodeRecord>(`/api/v1/nodes/${id}`),
  activateNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/activate`, { method: 'POST' }),
  standbyNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/standby`, { method: 'POST' }),
  drainNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/drain`, { method: 'POST' }),
  dispatchTask: async (taskType: string, assignedNodeId: string, seed = 42, payload?: any) => {
    const raw = await fetchJson<any>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify({
        idempotency_key: `task-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        task_type: taskType,
        origin_node_id: 'NODE-TANISH',
        assigned_node_id: assignedNodeId,
        seed,
        payload: payload || { cells: 100, horizons: [15, 30] },
      }),
    });
    return normalizeTask(raw);
  },
  getTasks: async (nodeId?: string) => {
    const q = nodeId ? `?node_id=${nodeId}` : '';
    const raw = await fetchJson<any[]>(`/api/v1/tasks${q}`);
    return (raw || []).map(normalizeTask);
  },

  // Verification & Audit
  runVerification: (simId: string, planId: string, horizonTicks = 6) =>
    fetchJson<VerificationResponse>('/api/v1/verification/run', {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        plan_id: planId,
        horizon_ticks: horizonTicks,
      }),
    }),
  getVerifications: (planId?: string) => {
    const q = planId ? `?plan_id=${planId}` : '';
    return fetchJson<VerificationResponse[]>(`/api/v1/verification${q}`);
  },
  getAuditLogs: (limit = 100) => fetchJson<AuditRecord[]>(`/api/v1/audit?limit=${limit}`),

  // EventSense Source Registry
  getSourceRegistry: (platform?: string, enabledOnly = false) => {
    const q = new URLSearchParams();
    if (platform) q.set('platform', platform);
    if (enabledOnly) q.set('enabled_only', 'true');
    const qs = q.toString() ? `?${q.toString()}` : '';
    return fetchJson<SourceRegistryItem[]>(`/api/v1/event-intelligence/sources/registry${qs}`);
  },
  testSourceConnector: (sourceId: string) =>
    fetchJson<{
      source_id: string;
      connector_type: string;
      health_status: string;
      message: string;
      last_check_at: string;
      latency_ms?: number | null;
    }>(`/api/v1/event-intelligence/sources/registry/${sourceId}/test`, { method: 'POST' }),

  // Geospatial Event-to-Cell Impact Assessment (Phase 5)
  getImpactEvents: (params?: { category?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.status) q.set('status', params.status);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return fetchJson<EventImpactSummary[]>(`/api/v1/event-intelligence/impact/events${qs}`);
  },
  getEventImpactDetail: (eventId: string) =>
    fetchJson<EventImpactSummary>(`/api/v1/event-intelligence/impact/events/${eventId}`),
  getCellImpacts: (params?: { region?: string; risk_band?: string; only_affected?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.region) q.set('region', params.region);
    if (params?.risk_band) q.set('risk_band', params.risk_band);
    if (params?.only_affected) q.set('only_affected', 'true');
    const qs = q.toString() ? `?${q.toString()}` : '';
    return fetchJson<CellImpactAggregated[]>(`/api/v1/event-intelligence/impact/cells${qs}`);
  },
  getCellImpactDetail: (cellId: string) =>
    fetchJson<CellImpactAggregated>(`/api/v1/event-intelligence/impact/cells/${cellId}`),
  getImpactOverlaps: () =>
    fetchJson<CellOverlapSummary[]>('/api/v1/event-intelligence/impact/overlaps'),
  recalculateImpacts: (networkId?: string) =>
    fetchJson<ImpactRecalculateResponse>('/api/v1/event-intelligence/impact/recalculate', {
      method: 'POST',
      body: JSON.stringify({ network_id: networkId }),
    }),
};
