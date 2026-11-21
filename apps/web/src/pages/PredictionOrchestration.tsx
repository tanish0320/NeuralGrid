import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronRight,
  Clock,
  Compass,
  Cpu,
  Layers,
  Play,
  RotateCcw,
  ShieldAlert,
  Sliders,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import {
  CellRecord,
  PlanRecord,
  PredictionsResponse,
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
  const [isLoadingPreds, setIsLoadingPreds] = useState<boolean>(false);
  const [isGeneratingPlan, setIsGeneratingPlan] = useState<boolean>(false);
  const [isActing, setIsActing] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);

  const activeCellId = selectedCellId || 'CELL-BLR-018';

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

  useEffect(() => {
    loadData();
  }, [simState?.simulation_id, simState?.state_version]);

  // Handle Generate Plan
  const handleGeneratePlan = async () => {
    if (!simState) return;
    setIsGeneratingPlan(true);
    try {
      const newPlan = await api.generatePlan(
        simState.simulation_id,
        simState.state_version,
        'Protect event-area connectivity & mitigate cell surge'
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
                  Forecast for {activeCellId}
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
                    <div key={tf.horizon_min} className="flex items-center justify-between p-1.5 rounded bg-noc-bg/60 border border-noc-border/50">
                      <span className="text-slate-400">+{tf.horizon_min}m Horizon:</span>
                      <div className="text-right">
                        <span className="font-bold text-slate-100">{tf.predicted_value.toFixed(1)} Mbps</span>
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
                    <div key={lf.horizon_min} className="flex items-center justify-between p-1.5 rounded bg-noc-bg/60 border border-noc-border/50">
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
                <AlertTriangle className="w-4 h-4 text-noc-amber" />
                <span className="text-xs font-semibold text-slate-200">
                  Risk Attribution for {activeCellId}
                </span>
              </div>
              <Badge
                type={activeRisk?.risk_band || 'LOW'}
                label={activeRisk?.risk_band || 'LOW'}
              />
            </div>

            <div className="mt-3 space-y-2 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2 bg-noc-card/70 p-2.5 rounded border border-noc-border">
                <div>
                  <span className="text-slate-500 text-[10px]">CURRENT UTIL:</span>
                  <div className="text-slate-200 font-bold">{activeRisk?.current_utilisation_pct?.toFixed(1) || 0}%</div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px]">FORECAST PEAK:</span>
                  <div className="text-red-400 font-bold">{activeRisk?.forecast_utilisation_pct?.toFixed(1) || 0}%</div>
                </div>
              </div>

              <div className="text-slate-300 text-xs font-semibold mt-2">Active Risk Drivers:</div>
              {activeRisk?.drivers && activeRisk.drivers.length > 0 ? (
                <div className="space-y-1.5">
                  {activeRisk.drivers.map((d, i) => (
                    <div key={i} className="p-2 rounded bg-noc-bg/80 border border-noc-border/60 text-[11px]">
                      <div className="flex justify-between text-slate-300 font-semibold">
                        <span>{d.feature}</span>
                        <span className="text-noc-cyan">{typeof d.value === 'number' ? d.value.toFixed(1) : d.value}</span>
                      </div>
                      <div className="text-slate-400 text-[10px] mt-0.5">{d.description}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-slate-500 text-[11px] p-2 bg-noc-card/40 rounded">
                  No critical threshold violations detected. Cell is within safe margin.
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
                  {selectedPlan?.intent || 'Mitigate event surge & preserve emergency SLA'}
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
                <Badge
                  type="SIMULATED_ACTION"
                  label={selectedPlan?.status || 'NO PLAN'}
                />
              </div>

              {selectedPlan ? (
                <div className="space-y-2 max-h-[220px] overflow-y-auto">
                  {selectedPlan.actions.map((act) => (
                    <div
                      key={act.action_id}
                      className="p-2.5 rounded bg-noc-card border border-noc-border text-xs font-mono space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-noc-cyan text-[11px]">{act.action_type}</span>
                        <span className="text-slate-300 font-semibold">{act.offload_mbps} Mbps</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        <span>Source: {act.source_cell_id || 'N/A'}</span>
                        <ChevronRight className="w-3 h-3 text-slate-600" />
                        <span>Target: {act.target_cell_id || 'NODE-JUNAID'}</span>
                      </div>
                      <div className="flex items-center justify-between text-[9px] text-slate-500 pt-1 border-t border-noc-divider">
                        <span>Expected Util Delta: {act.expected_delta_util_pct}%</span>
                        <span>Latency Delta: {act.expected_delta_latency_ms} ms</span>
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
