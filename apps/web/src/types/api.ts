export type RiskBand = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
export type CellOperationalState = 'ACTIVE' | 'STANDBY' | 'FAILED' | 'DEGRADED';
export type EventOrigin = 'SOURCE_DISCOVERED' | 'MANUAL_INPUT' | 'SEEDED_DEMO';
export type VerificationStatus = 'UNVERIFIED' | 'SINGLE_SOURCE' | 'CORROBORATED' | 'MANUALLY_VERIFIED' | 'DEMO_SCENARIO';
export type PlanStatus =
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'EXECUTED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'FAILED'
  | 'STALE';
export type NodeState = 'DISCONNECTED' | 'REGISTERING' | 'STANDBY' | 'ACTIVATING' | 'ACTIVE' | 'DRAINING' | 'DEGRADED' | 'OFFLINE' | 'ERROR';
export type TaskState = 'PENDING' | 'ASSIGNED' | 'ACCEPTED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'REJECTED' | 'CANCELLED' | 'RETRY_PENDING' | 'EXPIRED';

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
  event_id?: string | null;
  seed?: number;
  version?: number;
  state_version: number;
  intent: string;
  status: PlanStatus;
  solver_method?: string;
  objective_score: number;
  objective?: any;
  constraints_checked?: { name: string; passed: boolean; detail: string }[];
  explanation?: string[];
  actions: PlanAction[];
  constraints_passed: boolean;
  constraint_violations: string[];
  rejection_reason: string | null;
  created_at: string;
  expires_at: string;
  updated_at?: string;
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
  status: TaskState;
  state: TaskState;
  payload_sha256?: string;
  checksum: string | null;
  result_sha256: string | null;
  result?: Record<string, any> | null;
  retry_count?: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string;
  assigned_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms: number | null;
  verified?: boolean;
}

export interface SimulationBranchMetrics {
  congested_cell_minutes: number;
  peak_utilisation_pct: number;
  simulated_latency_p50_ms: number;
  simulated_latency_p95_ms: number;
  simulated_latency_max_ms: number;
  total_queued_mbps: number;
  total_unserved_mbps: number;
  total_energy_units: number;
  action_count: number;
}

export interface TwinNodeExecutionMetrics {
  tasks_total: number;
  tasks_completed: number;
  tasks_failed_or_pending: number;
  avg_duration_ms: number;
  total_retries: number;
  executed_nodes: string[];
  label: string;
}

export interface VerificationResponse {
  verification_id: string;
  baseline_run_id: string;
  intervention_run_id: string;
  plan_id: string;
  event_id: string | null;
  seed: number;
  initial_state_version: number;
  horizon_ticks: number;
  config_match: boolean;
  label: string;
  baseline: SimulationBranchMetrics;
  intervention: SimulationBranchMetrics;
  deltas: Record<string, number>;
  twinnode_metrics: TwinNodeExecutionMetrics;
  created_at: string;
}

export interface SourceRegistryItem {
  source_id: string;
  platform: string;
  display_name: string;
  base_url: string;
  connector_type: string;
  enabled: boolean;
  access_method: string;
  refresh_interval_sec: number;
  geographic_scope: string;
  supported_categories: string[];
  last_collected_at: string | null;
  last_error: string | null;
  health_status: 'HEALTHY' | 'DEGRADED' | 'UNAVAILABLE' | 'AWAITING_CREDENTIALS' | 'DISABLED';
  created_at: string;
  updated_at: string;
}

export interface AuditRecord {
  id: string;
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

export interface EventCellImpactRecord {
  impact_id: string;
  event_id: string;
  cell_id: string;
  geographic_distance_km: number;
  geographic_relevance_score: number;
  coverage_relevance_score: number;
  estimated_demand_delta_mbps: number;
  impact_confidence: number;
  impact_category: 'PRIMARY_HOTSPOT' | 'SECONDARY_ADJACENT' | 'PERIPHERAL_TRANSIT';
  impact_window_start: string;
  impact_window_end: string;
  temporal_profile: {
    arrival_hours: number;
    event_hours: number;
    departure_hours: number;
    peak_multiplier: number;
    effective_attendance: number;
    attendance_estimated: boolean;
    sample_points: Array<{
      timestamp: string;
      offset_minutes: number;
      surge_factor: number;
      demand_mbps: number;
    }>;
  };
  mapping_method: string;
  scoring_model_version: string;
  input_evidence_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface EventImpactSummary {
  event_id: string;
  event_title: string;
  event_category: string;
  venue_name: string | null;
  latitude: number | null;
  longitude: number | null;
  lifecycle_status: string;
  verification_status: string;
  attendance_estimate: number | null;
  is_geographically_resolved: boolean;
  total_affected_cells: number;
  total_demand_delta_mbps: number;
  impact_window_start: string | null;
  impact_window_end: string | null;
  affected_cells: EventCellImpactRecord[];
}

export interface ContributingEventInfo {
  event_id: string;
  event_title: string;
  event_category: string;
  venue_name: string | null;
  distance_km: number;
  demand_delta_mbps: number;
  impact_category: string;
  impact_confidence: number;
  impact_window_start: string;
  impact_window_end: string;
}

export interface CellImpactAggregated {
  cell_id: string;
  region: string;
  capacity_mbps: number;
  base_load_mbps: number;
  current_load_mbps: number;
  combined_demand_delta_mbps: number;
  projected_total_demand_mbps: number;
  projected_utilisation_pct: number;
  congestion_risk_band: 'NORMAL' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
  contributing_event_count: number;
  contributing_events: ContributingEventInfo[];
  max_impact_window_start: string | null;
  max_impact_window_end: string | null;
}

export interface CellOverlapSummary {
  cell_id: string;
  region: string;
  overlapping_event_count: number;
  event_ids: string[];
  event_titles: string[];
  individual_demand_sum_mbps: number;
  sublinear_aggregated_demand_mbps: number;
  attenuation_discount_mbps: number;
  peak_overlap_window_start: string | null;
  peak_overlap_window_end: string | null;
  risk_band: 'NORMAL' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
}

export interface HorizonMetricDetail {
  horizon_min: number;
  target_at: string;
  traffic_mbps: number;
  traffic_p10: number;
  traffic_p50: number;
  traffic_p90: number;
  latency_ms: number;
  latency_p10: number;
  latency_p50: number;
  latency_p90: number;
  projected_utilisation_pct: number;
  risk_band: RiskBand;
}

export interface CellForecastDetailResponse {
  cell_id: string;
  region: string;
  capacity_mbps: number;
  backhaul_capacity_mbps: number;
  current_demand_mbps: number;
  current_utilisation_pct: number;
  current_latency_ms: number;
  risk_band: RiskBand;
  horizons: HorizonMetricDetail[];
  contributing_events: any[];
  forecast_reasoning: string;
  model_version: string;
  generated_at: string;
}

export interface NetworkForecastSummaryResponse {
  simulation_id: string | null;
  state_version: number;
  total_cells: number;
  horizons: number[];
  congested_cells_by_horizon: Record<string, number>;
  max_demand_by_horizon: Record<string, number>;
  avg_demand_by_horizon: Record<string, number>;
  critical_cells: string[];
  high_risk_cells: string[];
  generated_at: string;
}

export interface ImpactRecalculateResponse {
  status: string;
  network_id: string | null;
  total_canonical_events: number;
  mapped_events_count: number;
  geographically_unresolved_count: number;
  excluded_events_count: number;
  total_impact_records: number;
  affected_cells_count: number;
  overlapping_cells_count: number;
  max_cell_demand_delta_mbps: number;
  avg_cell_demand_delta_mbps: number;
  category_distribution: Record<string, number>;
  timestamp: string;
}

