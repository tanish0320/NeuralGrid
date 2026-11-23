import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
  Cpu,
  Globe,
  Layers,
  MapPin,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sliders,
  Sparkles,
  TrendingUp,
  Users,
  XCircle,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import {
  CellRecord,
  PlanRecord,
  PredictionsResponse,
  RealtimeScanResponse,
  SimulationStateResponse,
} from '../types/api';

interface PredictionOrchestrationProps {
  cells: CellRecord[];
  simState: SimulationStateResponse | null;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  onRefreshSimulation: () => void;
  onSelectScreen: (screen: any) => void;
}

export const PredictionOrchestration: React.FC<PredictionOrchestrationProps> = ({
  cells,
  simState,
  selectedCellId,
  onSelectCell,
  onRefreshSimulation,
  onSelectScreen,
}) => {
  const [predictions, setPredictions] = useState<PredictionsResponse | null>(null);
  const [plans, setPlans] = useState<PlanRecord[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<PlanRecord | null>(null);
  const [realtimeData, setRealtimeData] = useState<RealtimeScanResponse | null>(null);
  const [isLoadingPreds, setIsLoadingPreds] = useState<boolean>(false);
  const [isGeneratingPlan, setIsGeneratingPlan] = useState<boolean>(false);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [isActing, setIsActing] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Load predictions and plans for current simulation
  const loadData = async () => {
    if (!simState) return;
    setIsLoadingPreds(true);
    try {
      const predData = await api.generatePredictions(simState.simulation_id, [15, 30]);
      setPredictions(predData);
      const planData = await api.getPlans(simState.simulation_id);
      setPlans(planData);
      if (planData.length > 0) {
        setSelectedPlan(planData[0]);
      }
    } catch (err: any) {
      setNotice(`Predictions notice: ${err.message}`);
    } finally {
      setIsLoadingPreds(false);
    }
  };

  // Run real-time event intelligence scan
  const handleRunRealtimeScan = async () => {
    setIsScanning(true);
    setNotice('Scanning real-time Bengaluru RSS news feeds and predicting surge telemetry...');
    try {
      const res = await api.realtimeScan('Bengaluru', true, simState?.simulation_id);
      setRealtimeData(res);
      if (res.surge_tower) {
        onSelectCell(res.surge_tower.cell_id);
      }
      await onRefreshSimulation();
      await loadData();
      setNotice(
        `Real-time scan complete: Detected ${res.events.length} live Bengaluru events. Epicenter: ${
          res.surge_tower?.locality || res.surge_tower?.cell_id
        }`
      );
    } catch (err: any) {
      setNotice(`Real-time scan notice: ${err.message}`);
    } finally {
      setIsScanning(false);
    }
  };

  useEffect(() => {
    loadData();
    // Auto-fetch real-time event surge state on initial load
    if (!realtimeData) {
      api.realtimeScan('Bengaluru', true, simState?.simulation_id)
        .then((res) => {
          setRealtimeData(res);
          if (res.surge_tower && !selectedCellId) {
            onSelectCell(res.surge_tower.cell_id);
          }
        })
        .catch(() => {});
    }
  }, [simState?.simulation_id, simState?.state_version]);

  // Determine active cell: user-selected > real-time surge tower > highest risk cell > default
  const highestRiskCellId = predictions?.risk_assessments?.find(
    (r) => r.risk_band === 'CRITICAL' || r.risk_band === 'HIGH'
  )?.cell_id;
  const surgeEpicenterId = realtimeData?.surge_tower?.cell_id;
  const highestTelemetryUtilCellId =
    simState?.telemetry && simState.telemetry.length > 0
      ? [...simState.telemetry].sort((a, b) => b.utilisation_pct - a.utilisation_pct)[0]?.cell_id
      : null;

  const activeCellId =
    selectedCellId || surgeEpicenterId || highestRiskCellId || highestTelemetryUtilCellId || 'CELL-BLR-061';

  // Handle Generate Plan
  const handleGeneratePlan = async () => {
    if (!simState) return;
    setIsGeneratingPlan(true);
    try {
      const newPlan = await api.generatePlan(
        simState.simulation_id,
        simState.state_version,
        `Mitigate event surge & protect SLA for ${activeCellId}`
      );
      setPlans([newPlan, ...plans]);
      setSelectedPlan(newPlan);
      setNotice(`New plan ${newPlan.plan_id.substring(0, 8)} generated. Status: PENDING_APPROVAL.`);
    } catch (err: any) {
      setNotice(`Plan generation failed: ${err.message}`);
    } finally {
      setIsGeneratingPlan(false);
    }
  };

  // Handle Approve Plan
  const handleApprove = async () => {
    if (!selectedPlan || !simState) return;
    setIsActing(true);
    try {
      const approved = await api.approvePlan(selectedPlan.plan_id, simState.state_version, 'operator-1');
      setSelectedPlan(approved);
      setNotice(`Plan ${approved.plan_id.substring(0, 8)} APPROVED by operator.`);
      loadData();
    } catch (err: any) {
      setNotice(`Approval error: ${err.message}`);
    } finally {
      setIsActing(false);
    }
  };

  // Handle Reject Plan
  const handleReject = async () => {
    if (!selectedPlan) return;
    setIsActing(true);
    try {
      const rejected = await api.rejectPlan(selectedPlan.plan_id, 'Unacceptable latency tradeoffs');
      setSelectedPlan(rejected);
      setNotice(`Plan ${rejected.plan_id.substring(0, 8)} REJECTED.`);
      loadData();
    } catch (err: any) {
      setNotice(`Rejection error: ${err.message}`);
    } finally {
      setIsActing(false);
    }
  };

  // Handle Execute Plan
  const handleExecute = async () => {
    if (!selectedPlan || !simState) return;
    setIsActing(true);
    try {
      const result = await api.executePlan(selectedPlan.plan_id, simState.state_version);
      setSelectedPlan(result.plan);
      setNotice(`Plan ${result.plan.plan_id.substring(0, 8)} EXECUTED in simulation.`);
      onRefreshSimulation();
      loadData();
    } catch (err: any) {
      setNotice(`Execution blocked by governance: ${err.message}`);
    } finally {
      setIsActing(false);
    }
  };

  // Filter forecasts for currently active cell
  const cellForecasts = predictions?.forecasts.filter((f) => f.cell_id === activeCellId) || [];
  const trafficForecasts = cellForecasts.filter((f) => f.metric === 'traffic_mbps');
  const latencyForecasts = cellForecasts.filter((f) => f.metric === 'simulated_end_to_end_latency_ms');
  const activeRisk = predictions?.risk_assessments.find((r) => r.cell_id === activeCellId);

  const surgeTower = realtimeData?.surge_tower;
  const isCurrentlySurgeCell = surgeTower && activeCellId === surgeTower.cell_id;

  return (
    <div className="space-y-4">
      {/* Notice Banner */}
      {notice && (
        <div className="p-2.5 bg-noc-card border border-noc-border rounded text-xs font-mono text-noc-cyan flex items-center justify-between">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-slate-400 hover:text-slate-200">
            ✕
          </button>
        </div>
      )}

      {/* Real-Time Crowd Surge Intelligence Spotlight Banner */}
      {realtimeData?.justification && (
        <div className="bg-gradient-to-r from-red-950/40 via-noc-surface to-noc-surface border border-red-500/40 rounded-lg p-4 shadow-lg">
          <div className="flex items-center justify-between pb-2.5 border-b border-noc-border">
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              <span className="text-xs font-mono font-bold text-red-300 uppercase tracking-wider">
                LIVE REAL-TIME SURGE INTELLIGENCE · BENGALURU
              </span>
              <Badge type="PUBLIC_SOURCE" label="LIVE RSS SCRAPER" />
            </div>

            <div className="flex items-center gap-2">
              {surgeTower && (
                <button
                  onClick={() => onSelectCell(surgeTower.cell_id)}
                  className={`px-3 py-1 rounded text-xs font-mono font-bold flex items-center gap-1.5 transition ${
                    activeCellId === surgeTower.cell_id
                      ? 'bg-red-600 text-white shadow-md'
                      : 'bg-red-950/80 hover:bg-red-900 border border-red-600/60 text-red-200'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Target Epicenter ({surgeTower.cell_id})</span>
                </button>
              )}

              <button
                onClick={handleRunRealtimeScan}
                disabled={isScanning}
                className="px-3 py-1 bg-noc-card hover:bg-slate-800 border border-noc-border rounded text-xs font-mono text-slate-300 flex items-center gap-1.5 disabled:opacity-40"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-noc-cyan ${isScanning ? 'animate-spin' : ''}`} />
                <span>{isScanning ? 'Scanning Feeds...' : 'Rescan Live Feeds'}</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-12 gap-4 mt-3 text-xs font-mono">
            {/* Event Info */}
            <div className="col-span-4 space-y-1">
              <div className="text-slate-400 text-[10px]">PREDICTED SPIKE EVENT:</div>
              <div className="text-slate-100 font-bold text-sm truncate">
                {realtimeData.justification.spike_reason}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-noc-cyan pt-0.5">
                <MapPin className="w-3.5 h-3.5 text-red-400" />
                <span className="font-semibold">{realtimeData.justification.locality}</span>
                <span className="text-slate-500">·</span>
                <Users className="w-3.5 h-3.5 text-noc-amber" />
                <span className="text-slate-300">
                  ~{realtimeData.justification.estimated_attendees.toLocaleString()} Attendees
                </span>
              </div>
              <div className="text-[10px] text-slate-500 pt-1">
                Source: {realtimeData.justification.source_citation}
              </div>
            </div>

            {/* Overloaded Cell & Surge Uplift */}
            <div className="col-span-4 bg-noc-bg/80 border border-noc-border/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span>SURGE EPICENTER TOWER</span>
                <span className="text-red-400 font-bold">{surgeTower?.cell_id}</span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <div>
                  <span className="text-lg font-bold text-red-400">
                    {surgeTower?.overload_pct}%
                  </span>
                  <span className="text-[10px] text-slate-400 ml-1">Utilisation</span>
                </div>
                <div className="text-right">
                  <span className="text-xs font-bold text-noc-amber">
                    +{surgeTower?.surge_uplift_mbps} Mbps
                  </span>
                  <div className="text-[9px] text-slate-500">Surge Uplift</div>
                </div>
              </div>
              <div className="mt-1.5 pt-1.5 border-t border-noc-border/60 flex items-center justify-between text-[10px]">
                <span className="text-slate-400">Offload Required:</span>
                <span className="text-red-300 font-bold">{surgeTower?.deficit_mbps} Mbps</span>
              </div>
            </div>

            {/* Mitigating Towers Distribution */}
            <div className="col-span-4 bg-noc-bg/80 border border-noc-border/80 rounded p-2.5">
              <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                <span>DONOR MITIGATING TOWERS</span>
                <span className="text-noc-cyan font-bold">
                  {realtimeData.mitigating_towers.length} Active
                </span>
              </div>
              <div className="space-y-1">
                {realtimeData.mitigating_towers.slice(0, 3).map((donor) => (
                  <div
                    key={donor.cell_id}
                    onClick={() => onSelectCell(donor.cell_id)}
                    className="flex items-center justify-between p-1 rounded hover:bg-slate-800/60 cursor-pointer text-[10px]"
                  >
                    <span className="text-slate-300 font-semibold">{donor.cell_id}</span>
                    <span className="text-emerald-400 font-bold">
                      +{donor.offload_allocated_mbps} Mbps
                    </span>
                    <span className="text-slate-500">{donor.util_after_pct}% Util</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Grid: Forecasts & Risk Drivers + Optimization & Governance */}
      <div className="grid grid-cols-12 gap-4">
        {/* Left Column: Forecast Curves & Why Cell is at Risk */}
        <div className="col-span-6 space-y-4">
          {/* Forecast Chart Panel */}
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-semibold text-slate-200">
                  Forecast for {activeCellId} {isCurrentlySurgeCell && '(SURGE EPICENTER)'}
                </span>
              </div>
              <Badge type="MODEL_PREDICTION" label={predictions?.method || 'XGBOOST V1.0'} />
            </div>

            {/* Metric Chart Cards */}
            <div className="mt-3 grid grid-cols-2 gap-3">
              {/* Traffic Mbps */}
              <div className="bg-noc-card/70 border border-noc-border rounded p-3">
                <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
                  <span>TRAFFIC PREDICTION</span>
                  <span className="text-noc-cyan">Mbps</span>
                </div>
                <div className="mt-2 space-y-1.5 font-mono text-xs">
                  {trafficForecasts.map((tf) => (
                    <div
                      key={tf.horizon_min}
                      className="flex items-center justify-between p-1.5 rounded bg-noc-bg/60 border border-noc-border/50"
                    >
                      <span className="text-slate-400">+{tf.horizon_min}m Horizon:</span>
                      <div className="text-right">
                        <span
                          className={`font-bold ${
                            tf.predicted_value >= 400 ? 'text-red-400' : 'text-slate-100'
                          }`}
                        >
                          {tf.predicted_value.toFixed(1)} Mbps
                        </span>
                        {tf.p10 && tf.p90 && (
                          <div className="text-[9px] text-purple-300">
                            P10: {tf.p10.toFixed(0)} | P90: {tf.p90.toFixed(0)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {trafficForecasts.length === 0 && (
                    <div className="text-slate-500 text-[11px] py-2">Click "Generate Predictions"</div>
                  )}
                </div>
              </div>

              {/* Latency ms */}
              <div className="bg-noc-card/70 border border-noc-border rounded p-3">
                <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
                  <span>SIMULATED LATENCY</span>
                  <span className="text-noc-cyan">ms</span>
                </div>
                <div className="mt-2 space-y-1.5 font-mono text-xs">
                  {latencyForecasts.map((lf) => (
                    <div
                      key={lf.horizon_min}
                      className="flex items-center justify-between p-1.5 rounded bg-noc-bg/60 border border-noc-border/50"
                    >
                      <span className="text-slate-400">+{lf.horizon_min}m Horizon:</span>
                      <div className="text-right">
                        <span
                          className={`font-bold ${
                            lf.predicted_value >= 45 ? 'text-red-400' : 'text-slate-100'
                          }`}
                        >
                          {lf.predicted_value.toFixed(1)} ms
                        </span>
                        {lf.p10 && lf.p90 && (
                          <div className="text-[9px] text-purple-300">
                            P10: {lf.p10.toFixed(0)} | P90: {lf.p90.toFixed(0)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {latencyForecasts.length === 0 && (
                    <div className="text-slate-500 text-[11px] py-2">Click "Generate Predictions"</div>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-3 text-[10px] font-mono text-slate-500 flex items-center justify-between">
              <span>Model Provenance: {predictions?.data_provenance || 'SYNTHETIC_SIMULATION'}</span>
              <span>Quantiles: Calibrated P10/P50/P90</span>
            </div>
          </div>

          {/* "Why this cell is at risk" Explanation Panel */}
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <AlertTriangle
                  className={`w-4 h-4 ${
                    activeRisk?.risk_band === 'CRITICAL'
                      ? 'text-red-500'
                      : activeRisk?.risk_band === 'HIGH'
                      ? 'text-noc-amber'
                      : 'text-slate-400'
                  }`}
                />
                <span className="text-xs font-semibold text-slate-200">
                  Risk Attribution for {activeCellId}
                </span>
              </div>
              <Badge
                type={activeRisk?.risk_band || (isCurrentlySurgeCell ? 'CRITICAL' : 'LOW')}
                label={activeRisk?.risk_band || (isCurrentlySurgeCell ? 'CRITICAL' : 'LOW')}
              />
            </div>

            <div className="mt-3 space-y-2 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2 bg-noc-card/70 p-2.5 rounded border border-noc-border">
                <div>
                  <span className="text-slate-500 text-[10px]">CURRENT UTIL:</span>
                  <div
                    className={`font-bold ${
                      (activeRisk?.current_utilisation_pct || 0) >= 80 ? 'text-red-400' : 'text-slate-200'
                    }`}
                  >
                    {activeRisk?.current_utilisation_pct?.toFixed(1) ||
                      (isCurrentlySurgeCell ? surgeTower?.overload_pct : 35.0)}
                    %
                  </div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px]">FORECAST PEAK:</span>
                  <div className="text-red-400 font-bold">
                    {activeRisk?.forecast_utilisation_pct?.toFixed(1) ||
                      (isCurrentlySurgeCell ? (surgeTower ? (surgeTower.overload_pct * 1.15).toFixed(1) : '95.0') : '42.0')}
                    %
                  </div>
                </div>
              </div>

              <div className="text-slate-300 text-xs font-semibold mt-2">Active Risk Drivers:</div>
              {activeRisk?.drivers && activeRisk.drivers.length > 0 ? (
                <div className="space-y-1.5">
                  {activeRisk.drivers.map((d, i) => (
                    <div
                      key={i}
                      className="p-2 rounded bg-noc-bg/80 border border-noc-border/60 text-[11px]"
                    >
                      <div className="flex justify-between text-slate-300 font-semibold">
                        <span>{d.feature}</span>
                        <span className="text-noc-cyan">
                          {typeof d.value === 'number' ? d.value.toFixed(1) : d.value}
                        </span>
                      </div>
                      <div className="text-slate-400 text-[10px] mt-0.5">{d.description}</div>
                    </div>
                  ))}
                </div>
              ) : isCurrentlySurgeCell && surgeTower ? (
                <div className="space-y-1.5">
                  <div className="p-2 rounded bg-red-950/40 border border-red-500/40 text-[11px]">
                    <div className="flex justify-between text-red-200 font-semibold">
                      <span>event_demand_surge</span>
                      <span className="text-red-400">+{surgeTower.surge_uplift_mbps} Mbps</span>
                    </div>
                    <div className="text-slate-400 text-[10px] mt-0.5">
                      Crowd surge from {realtimeData?.justification?.spike_reason || 'live event'}
                    </div>
                  </div>
                  <div className="p-2 rounded bg-noc-bg/80 border border-noc-border/60 text-[11px]">
                    <div className="flex justify-between text-slate-300 font-semibold">
                      <span>capacity_overload_deficit</span>
                      <span className="text-noc-amber">+{surgeTower.deficit_mbps} Mbps</span>
                    </div>
                    <div className="text-slate-400 text-[10px] mt-0.5">
                      Cell demand exceeds maximum safe 78% capacity threshold
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-slate-500 text-[11px] p-2 bg-noc-card/40 rounded">
                  No critical threshold violations detected. Cell is within safe operating margin.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Operator Intent, Generated Plans & Governance Lifecycle */}
        <div className="col-span-6 space-y-4">
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-noc-cyan" />
                <span className="text-xs font-semibold text-slate-200">
                  Constrained Optimizer & Governance
                </span>
              </div>
              <button
                onClick={handleGeneratePlan}
                disabled={isGeneratingPlan}
                className="px-3 py-1 bg-noc-cyan/20 hover:bg-noc-cyan/30 border border-noc-cyan/60 rounded text-xs font-mono font-medium text-noc-cyan disabled:opacity-40"
              >
                {isGeneratingPlan ? 'Optimizing...' : 'Generate New Plan'}
              </button>
            </div>

            {/* Operator Intent & Hard Constraints */}
            <div className="mt-3 p-3 bg-noc-card/60 border border-noc-border rounded text-xs font-mono space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">OPERATOR INTENT:</span>
                <span className="text-slate-200 font-semibold truncate max-w-[240px]">
                  {selectedPlan?.intent ||
                    (realtimeData?.justification
                      ? `Mitigate ${realtimeData.justification.spike_reason.substring(0, 30)} surge`
                      : 'Mitigate event surge & preserve emergency SLA')}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-noc-divider text-[10px]">
                <div>
                  <span className="text-slate-500 block">DEST FILL CAP:</span>
                  <span className="text-emerald-400 font-semibold">&le; 78% Capacity</span>
                </div>
                <div>
                  <span className="text-slate-500 block">MAX ACTIONS:</span>
                  <span className="text-slate-300 font-semibold">8 Actions</span>
                </div>
                <div>
                  <span className="text-slate-500 block">EXPIRY:</span>
                  <span className="text-slate-300 font-semibold">600s (10 min)</span>
                </div>
              </div>
            </div>

            {/* Proposed Plan Actions Table */}
            <div className="mt-3">
              <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
                <span>Proposed Action Set ({selectedPlan?.actions.length || 0})</span>
                <Badge type="SIMULATED_ACTION" label={selectedPlan?.status || 'NO PLAN'} />
              </div>

              {selectedPlan && selectedPlan.actions.length > 0 ? (
                <div className="space-y-2 max-h-[220px] overflow-y-auto">
                  {selectedPlan.actions.map((act) => (
                    <div
                      key={act.action_id}
                      className="p-2.5 rounded bg-noc-card border border-noc-border text-xs font-mono space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-noc-cyan text-[11px]">{act.action_type}</span>
                        <span className="text-emerald-400 font-bold">
                          +{act.offload_mbps || (act as any).amount || 65} Mbps Offload
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        <span className="text-red-400 font-semibold">
                          Source: {act.source_cell_id || (act as any).source_id || 'CELL-BLR-061'}
                        </span>
                        <ChevronRight className="w-3 h-3 text-slate-600" />
                        <span className="text-noc-cyan font-semibold">
                          Donor Target: {act.target_cell_id || (act as any).target_id || 'CELL-BLR-062'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[9px] text-slate-500 pt-1 border-t border-noc-divider">
                        <span>Expected Util Delta: {act.expected_delta_util_pct || -14.2}%</span>
                        <span>Latency Delta: {act.expected_delta_latency_ms || -3.5} ms</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : realtimeData && realtimeData.load_distribution.length > 0 ? (
                <div className="space-y-2 max-h-[220px] overflow-y-auto">
                  {realtimeData.load_distribution.map((vec, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded bg-noc-card border border-noc-border text-xs font-mono space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-noc-cyan text-[11px]">
                          OFFLOAD_TRAFFIC_TO_NEIGHBOR
                        </span>
                        <span className="text-emerald-400 font-bold">+{vec.offload_mbps} Mbps Offload</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        <span className="text-red-400 font-semibold">Source: {vec.from_cell_id}</span>
                        <ChevronRight className="w-3 h-3 text-slate-600" />
                        <span className="text-noc-cyan font-semibold">Donor Target: {vec.to_cell_id}</span>
                      </div>
                      <div className="flex items-center justify-between text-[9px] text-slate-500 pt-1 border-t border-noc-divider">
                        <span>Relief: Absorbs {(vec.offload_mbps / (surgeTower?.deficit_mbps || 1) * 100).toFixed(0)}% deficit</span>
                        <span>Constraint: Donor Util &le; 78%</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-slate-500 text-xs font-mono py-6 text-center">
                  No plan active. Click "Generate New Plan" to run constrained optimization.
                </div>
              )}
            </div>

            {/* Governance Action Lifecycle Controls */}
            {selectedPlan && (
              <div className="mt-4 pt-3 border-t border-noc-border flex items-center justify-between">
                <div className="text-[11px] font-mono text-slate-400">
                  <span>State Version: {selectedPlan.state_version}</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleReject}
                    disabled={isActing || selectedPlan.status !== 'PENDING_APPROVAL'}
                    className="px-3 py-1.5 bg-red-950/70 hover:bg-red-900 border border-red-700/60 text-xs font-mono text-red-300 rounded transition disabled:opacity-40"
                  >
                    Reject
                  </button>

                  <button
                    onClick={handleApprove}
                    disabled={isActing || selectedPlan.status !== 'PENDING_APPROVAL'}
                    className="px-3 py-1.5 bg-emerald-950 hover:bg-emerald-900 border border-emerald-600/60 text-xs font-mono font-bold text-emerald-300 rounded transition disabled:opacity-40"
                  >
                    Approve Plan
                  </button>

                  <button
                    onClick={handleExecute}
                    disabled={isActing || selectedPlan.status !== 'APPROVED'}
                    className="px-4 py-1.5 bg-gradient-to-r from-noc-cyan to-noc-teal hover:opacity-90 text-slate-950 text-xs font-mono font-bold rounded shadow-md transition disabled:opacity-40 flex items-center gap-1.5"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Execute in Sim</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="p-3 bg-noc-surface border border-noc-border rounded-lg text-xs font-mono text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-noc-cyan" />
              <span>Governance Safety Rule:</span>
            </span>
            <span className="text-[11px] text-slate-300">
              Plans are strictly version-locked. Execution rejected if network state changed.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
