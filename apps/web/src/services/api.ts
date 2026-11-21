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
  SimulationStateResponse,
  TaskRecord,
  VerificationResponse,
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

export const api = {
  // Health
  getHealth: () => fetchJson<HealthResponse>('/health'),

  // Networks & Graph
  seedNetwork: (seed = 42, cellCount = 100) =>
    fetchJson<NetworkResponse>('/api/v1/networks/seed', {
      method: 'POST',
      body: JSON.stringify({ seed, cell_count: cellCount, force: true }),
    }),
  getCurrentNetwork: () => fetchJson<NetworkResponse>('/api/v1/networks/current'),
  getCurrentCells: () => fetchJson<{ network: any; cells: CellRecord[] }>('/api/v1/networks/current/cells'),
  getCurrentGraph: () => fetchJson<GraphResponse>('/api/v1/networks/current/graph'),

  // Simulations
  createSimulation: (seed = 42) =>
    fetchJson<SimulationStateResponse>('/api/v1/simulations', {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),
  getSimulationState: (simId: string) => fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/state`),
  stepSimulation: (simId: string, steps = 1) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/step`, {
      method: 'POST',
      body: JSON.stringify({ steps }),
    }),
  pauseSimulation: (simId: string) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/pause`, { method: 'POST' }),
  resumeSimulation: (simId: string) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/start`, { method: 'POST' }),
  resetSimulation: (simId: string, seed = 42) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/reset`, {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),
  injectEvent: (simId: string, eventId: string, radiusKm = 3.0, intensity = 1.5) =>
    fetchJson<SimulationStateResponse>(`/api/v1/simulations/${simId}/events`, {
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

  // Predictions & Risk
  generatePredictions: (simId: string, horizons = [15, 30], cellIds?: string[]) =>
    fetchJson<PredictionsResponse>('/api/v1/predictions/generate', {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        horizons,
        cell_ids: cellIds,
      }),
    }),
  getPredictions: (simId: string) => fetchJson<PredictionsResponse>(`/api/v1/predictions/${simId}`),

  // Plans & Governance
  generatePlan: (simId: string, stateVersion: number, intent = 'Protect event-area connectivity') =>
    fetchJson<PlanRecord>('/api/v1/plans/generate', {
      method: 'POST',
      body: JSON.stringify({
        simulation_id: simId,
        state_version: stateVersion,
        intent,
      }),
    }),
  getPlans: (simId?: string) => {
    const q = simId ? `?simulation_id=${simId}` : '';
    return fetchJson<PlanRecord[]>(`/api/v1/plans${q}`);
  },
  approvePlan: (planId: string, stateVersion: number, operatorId = 'operator-1') =>
    fetchJson<PlanRecord>(`/api/v1/plans/${planId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: operatorId,
        plan_version: 1,
        state_version: stateVersion,
        notes: 'Approved for event surge capacity offload',
      }),
    }),
  rejectPlan: (planId: string, reason = 'Operator rejected plan alternative') =>
    fetchJson<PlanRecord>(`/api/v1/plans/${planId}/reject`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: 'operator-1',
        reason,
      }),
    }),
  executePlan: (planId: string, expectedStateVersion: number) =>
    fetchJson<{ plan: PlanRecord; simulation_state: SimulationStateResponse }>(`/api/v1/plans/${planId}/execute`, {
      method: 'POST',
      body: JSON.stringify({
        operator_id: 'operator-1',
        expected_state_version: expectedStateVersion,
      }),
    }),

  // TwinNode
  getNodes: () => fetchJson<NodeRecord[]>('/api/v1/nodes'),
  getNode: (id: string) => fetchJson<NodeRecord>(`/api/v1/nodes/${id}`),
  activateNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/activate`, { method: 'POST' }),
  standbyNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/standby`, { method: 'POST' }),
  drainNode: (nodeId: string) =>
    fetchJson<NodeRecord>(`/api/v1/nodes/${nodeId}/drain`, { method: 'POST' }),
  dispatchTask: (taskType: string, assignedNodeId: string, seed = 42, payload?: any) =>
    fetchJson<TaskRecord>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify({
        idempotency_key: `task-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        task_type: taskType,
        origin_node_id: 'NODE-TANISH',
        assigned_node_id: assignedNodeId,
        seed,
        payload: payload || { cells: 100, horizons: [15, 30] },
      }),
    }),
  getTasks: (nodeId?: string) => {
    const q = nodeId ? `?node_id=${nodeId}` : '';
    return fetchJson<TaskRecord[]>(`/api/v1/tasks${q}`);
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
  getAuditLogs: (limit = 100) => fetchJson<AuditRecord[]>(`/api/v1/audit?limit=${limit}`),
};
