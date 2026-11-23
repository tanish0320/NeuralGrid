export type RiskBand = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
export type CellOperationalState = 'ACTIVE' | 'STANDBY' | 'FAILED' | 'DEGRADED';
export type EventOrigin = 'SOURCE_DISCOVERED' | 'MANUAL_INPUT' | 'SEEDED_DEMO';
export type VerificationStatus = 'UNVERIFIED' | 'SINGLE_SOURCE' | 'CORROBORATED' | 'MANUALLY_VERIFIED' | 'DEMO_SCENARIO';
export type PlanStatus = 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'EXPIRED' | 'STALE';
export type NodeState = 'DISCONNECTED' | 'STANDBY' | 'ACTIVATING' | 'ACTIVE' | 'DRAINING' | 'DEGRADED' | 'OFFLINE';
export type TaskState = 'PENDING' | 'ASSIGNED' | 'ACCEPTED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'REJECTED' | 'EXPIRED';

export interface HealthResponse {
  status: string;
  env: string;
  db_journal_mode: string;
  network_cell_count: number;
  registered_nodes: number;
  tanish_eventsense_service_loaded: boolean;
  timestamp: string;
}

export interface CellRecord {
  cell_id: string;
  network_id: string;
  region: string;
  latitude: number;
  longitude: number;
  lat?: number;
  lon?: number;
  capacity_mbps: number;
  backhaul_capacity_mbps?: number;
  base_load_mbps?: number;
  criticality: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  is_emergency_priority: boolean;
  is_emergency?: boolean;
  base_latency_ms: number;
  initial_state: CellOperationalState;
  current_state: CellOperationalState;
}

export interface CellEdgeRecord {
  edge_id: string;
  network_id: string;
  source_cell_id: string;
  target_cell_id: string;
  edge_type: string;
  distance_km?: number;
  weight: number;
  max_transfer_mbps?: number;
  enabled: boolean;
  id?: string;
  source?: string;
  target?: string;
  type?: string;
}

export interface NetworkResponse {
  network_id: string;
  seed: number;
  cell_count: number;
  created_at: string;
  cells: CellRecord[];
}

export interface GraphNode {
  id: string;
  label: string;
  region: string;
  criticality: string;
  capacity: number;
  cell_id?: string;
  capacity_mbps?: number;
  lat?: number;
  lon?: number;
  latitude?: number;
  longitude?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  distance?: number;
  edge_id?: string;
  source_cell_id?: string;
  target_cell_id?: string;
  edge_type?: string;
  weight?: number;
}

export interface GraphResponse {
  network_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  average_degree: number;
}

export interface CellTelemetryRecord {
  cell_id: string;
  tick: number;
  background_demand_mbps: number;
  event_demand_mbps: number;
  demand_mbps: number;
  served_mbps: number;
  queued_mbps: number;
  unserved_mbps: number;
  utilisation_pct: number;
  simulated_latency_ms: number;
  cell_state: CellOperationalState;
  sim_time_utc: string;
}

export interface SimulationSummary {
  total_cells: number;
  active_cells: number;
  standby_cells: number;
  failed_cells: number;
  congested_cells: number;
  total_demand_mbps: number;
  total_served_mbps: number;
  total_queued_mbps: number;
  total_unserved_mbps: number;
  peak_utilisation_pct: number;
  mean_simulated_latency_ms: number;
}

export interface SimulationStateResponse {
  simulation_id: string;
  network_id: string;
  seed: number;
  tick: number;
  state_version: number;
  status: 'INITIALIZED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'RESET';
  sim_time_utc: string;
  active_event_id: string | null;
  summary: SimulationSummary;
  telemetry: CellTelemetryRecord[];
  faults: Record<string, { fault_type: string; severity: number; active: boolean }>;
}

export interface EventRecord {
  event_id: string;
  event_key: string | null;
  event_origin: EventOrigin;
  name: string;
  event_type: string;
  venue_name: string | null;
  city: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  start_at: string | null;
  end_at: string | null;
  attendance_low: number | null;
  attendance_high: number | null;
  attendance_basis: 'SOURCE_EVIDENCE' | 'OPERATOR_ASSUMPTION' | 'UNKNOWN';
  intensity: number;
  verification_status: VerificationStatus;
  status: 'CANDIDATE' | 'CONFIRMED' | 'REJECTED';
  source_ids: string[];
  field_provenance: Record<string, any>;
  created_at: string;
}

export interface EventSourceRecord {
  source_id: string;
  discovery_run_id: string;
  event_id: string | null;
  discovery_provider: 'gdelt' | 'rss' | 'manual';
  fetch_provider: 'crawl4ai' | 'static_html_fallback' | null;
  source_type: string;
  url: string;
  canonical_url: string;
  domain: string;
  title: string | null;
  snippet: string | null;
  published_at: string | null;
  discovered_at: string;
  collected_at: string | null;
  fetch_status: string;
  extraction_status: string;
  evidence_summary: string | null;
  extracted_fields: Record<string, any>;
}

export interface EventImpactResponse {
  event_id: string;
  simulation_id: string;
  influence_radius_km: number;
  attendance_scenario: 'LOW' | 'EXPECTED' | 'HIGH';
  affected_cells: {
    cell_id: string;
    distance_km: number;
    impact_weight: number;
    estimated_additional_demand_mbps: number;
    reason: string;
  }[];
  total_estimated_uplift_mbps: number;
}

export interface ForecastRecord {
  run_id: string;
  event_id: string | null;
  state_version: number;
  cell_id: string;
  horizon_min: number;
  metric: 'traffic_mbps' | 'simulated_end_to_end_latency_ms';
  unit: 'Mbps' | 'ms';
  predicted_value: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  method: string;
  model_version: string;
  data_provenance: string;
  generated_at: string;
  target_at: string;
}

export interface RiskDriver {
  feature: string;
  value: number | string;
  threshold: number | string | null;
  description: string;
}

export interface CellRiskRecord {
  run_id: string;
  state_version: number;
  cell_id: string;
  risk_band: RiskBand;
  risk_method: string;
  current_utilisation_pct: number;
  forecast_utilisation_pct: number;
  current_latency_ms: number;
  forecast_latency_ms: number;
  drivers: RiskDriver[];
}

export interface PredictionsResponse {
  simulation_id: string;
  event_id: string | null;
  state_version: number;
  seed: number;
  method: string;
  model_version: string;
  data_provenance: string;
  forecasts: ForecastRecord[];
  risk_assessments: CellRiskRecord[];
}

export interface PlanAction {
  action_id: string;
  action_type: 'ACTIVATE_STANDBY_CELL' | 'OFFLOAD_TRAFFIC_TO_NEIGHBOR' | 'REDUCE_NON_CRITICAL_POWER' | 'DISPATCH_TWINNODE_TASK';
  source_cell_id: string | null;
  target_cell_id: string | null;
  offload_mbps: number | null;
  expected_delta_util_pct: number;
  expected_delta_latency_ms: number;
}

export interface PlanRecord {
  plan_id: string;
  simulation_id: string;
  state_version: number;
  intent: string;
  status: PlanStatus;
  objective_score: number;
  actions: PlanAction[];
  constraints_passed: boolean;
  constraint_violations: string[];
  rejection_reason: string | null;
  created_at: string;
  expires_at: string;
}

export interface NodeRecord {
  node_id: string;
  hostname: string;
  ip_address?: string;
  ip_last_seen?: string;
  port?: number;
  agent_url?: string;
  role?: string;
  status?: string;
  state: NodeState;
  assigned_cell_ids?: string[];
  last_heartbeat?: string;
  last_heartbeat_at?: string;
  heartbeat_age_seconds: number;
  consecutive_misses?: number;
  is_online: boolean;
  worker_active?: boolean;
  worker_slots?: number;
  latest_host_telemetry?: {
    cpu_pct?: number;
    ram_pct?: number;
    memory_pct?: number;
    rtt_ms?: number;
    local_rtt_ms?: number;
    worker_queue_depth?: number;
    label?: string;
  };
}

export interface TaskRecord {
  task_id: string;
  idempotency_key: string;
  task_type: string;
  origin_node_id: string;
  assigned_node_id: string;
  state: TaskState;
  payload_sha256: string;
  result_sha256: string | null;
  created_at: string;
  assigned_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  verified: boolean;
}

export interface VerificationResponse {
  verification_id: string;
  simulation_id: string;
  plan_id: string;
  horizon_ticks: number;
  seed: number;
  baseline_metrics: {
    total_congested_cell_minutes: number;
    peak_utilisation_pct: number;
    latency_p95_ms: number;
    unserved_demand_mbit: number;
    energy_units: number;
  };
  intervention_metrics: {
    total_congested_cell_minutes: number;
    peak_utilisation_pct: number;
    latency_p95_ms: number;
    unserved_demand_mbit: number;
    energy_units: number;
  };
  deltas: {
    congested_minutes_saved: number;
    peak_util_delta_pct: number;
    latency_p95_delta_ms: number;
    unserved_demand_saved_mbit: number;
  };
  twinnode_metrics: {
    tasks_dispatched: number;
    tasks_completed: number;
    total_compute_ms: number;
    checksums_verified: boolean;
  };
}

export interface AuditRecord {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  state_version: number | null;
  details: Record<string, any>;
}

export interface MitigatingTower {
  cell_id: string;
  region: string;
  locality: string;
  lat: number;
  lon: number;
  distance_km: number;
  capacity_mbps: number;
  base_load_mbps: number;
  headroom_before_mbps: number;
  offload_allocated_mbps: number;
  headroom_after_mbps: number;
  util_after_pct: number;
}

export interface SurgeTower {
  cell_id: string;
  region: string;
  locality: string;
  lat: number;
  lon: number;
  distance_to_venue_km: number;
  capacity_mbps: number;
  base_load_mbps: number;
  surge_uplift_mbps: number;
  total_demand_mbps: number;
  overload_pct: number;
  is_overloaded: boolean;
  deficit_mbps: number;
}

export interface LoadDistributionVector {
  from_cell_id: string;
  to_cell_id: string;
  from_coords: [number, number];
  to_coords: [number, number];
  offload_mbps: number;
  label: string;
}

export interface SurgeJustification {
  locality: string;
  spike_reason: string;
  event_window: string;
  estimated_attendees: number;
  source_citation: string;
  source_url: string;
  traffic_breakdown: {
    base_demand_mbps: number;
    surge_uplift_mbps: number;
    total_unmitigated_demand_mbps: number;
    tower_capacity_mbps: number;
    overload_pct: number;
    offload_required_mbps: number;
    total_offloaded_mbps: number;
  };
  hard_constraints: {
    backhaul_margin: string;
    latency_sla: string;
    handover_churn: string;
    standby_activation: string;
  };
}

export interface RealtimeScanResponse {
  status: string;
  discovered_sources_count: number;
  events: EventRecord[];
  selected_event: EventRecord | null;
  surge_tower: SurgeTower | null;
  mitigating_towers: MitigatingTower[];
  load_distribution: LoadDistributionVector[];
  justification: SurgeJustification;
}
