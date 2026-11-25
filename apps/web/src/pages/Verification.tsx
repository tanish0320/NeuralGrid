import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  Play,
  RotateCcw,
  ShieldCheck,
  TrendingDown,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import { PlanRecord, SimulationStateResponse, VerificationResponse } from '../types/api';

interface VerificationProps {
  simState: SimulationStateResponse | null;
  plans: PlanRecord[];
  onRefreshPlans?: () => void;
}

export const Verification: React.FC<VerificationProps> = ({ simState, plans, onRefreshPlans }) => {
  const [verification, setVerification] = useState<VerificationResponse | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [selectedPlanId, setSelectedPlanId] = useState<string>('');
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    onRefreshPlans?.();
  }, [simState?.simulation_id]);

  useEffect(() => {
    if (plans.length > 0 && (!selectedPlanId || !plans.some((p) => p.plan_id === selectedPlanId))) {
      setSelectedPlanId(plans[0].plan_id);
    }
  }, [plans]);

  useEffect(() => {
    if (!selectedPlanId) return;
    api
      .getVerifications(selectedPlanId)
      .then((list) => {
        if (list.length > 0) setVerification(list[0]);
        else setVerification(null);
      })
      .catch(() => {});
  }, [selectedPlanId]);

  const handleRunVerification = async () => {
    if (!simState || !selectedPlanId) return;
    setIsRunning(true);
    setMessage('Computing counterfactual rollout: Baseline (no action) vs. Operator Intervention...');
    try {
      const res = await api.runVerification(simState.simulation_id, selectedPlanId, 6);
      setVerification(res);
      setMessage(`Counterfactual verification completed (seed ${res.seed}, ${res.horizon_ticks} ticks).`);
    } catch (err: any) {
      setMessage(`Verification notice: ${err.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const base = verification?.baseline;
  const intv = verification?.intervention;
  const congestedSaved =
    base && intv ? Math.round((base.congested_cell_minutes - intv.congested_cell_minutes) * 10) / 10 : 0;
  const congestedPct =
    base && base.congested_cell_minutes > 0
      ? ((congestedSaved / base.congested_cell_minutes) * 100).toFixed(1)
      : '0.0';
  const energyDeltaPct =
    base && intv && base.total_energy_units > 0
      ? (((intv.total_energy_units - base.total_energy_units) / base.total_energy_units) * 100).toFixed(1)
      : '0.0';

  return (
    <div className="space-y-4">
      {/* Notice Banner */}
      {message && (
        <div className="p-2.5 bg-noc-card border border-noc-border rounded text-xs font-mono text-noc-cyan flex items-center justify-between">
          <span>{message}</span>
          <button onClick={() => setMessage(null)} className="text-slate-400 hover:text-slate-200">
            ✕
          </button>
        </div>
      )}

      {/* Control Strip */}
      <div className="bg-noc-surface border border-noc-border rounded-lg p-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          <div>
            <div className="text-xs font-bold text-slate-100 flex items-center gap-2">
              <span>Deterministic Counterfactual Verification Engine</span>
              <Badge type="SYNTHETIC" label="DIGITAL TWIN SIMULATION" />
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              Compares unmitigated baseline against operator-approved capacity intervention with matched initial state.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={selectedPlanId}
            onChange={(e) => setSelectedPlanId(e.target.value)}
            className="bg-noc-card border border-noc-border rounded px-2.5 py-1.5 text-xs font-mono text-slate-200"
          >
            {plans.length === 0 ? (
              <option value="">No plans generated yet</option>
            ) : (
              plans.map((p) => (
                <option key={p.plan_id} value={p.plan_id}>
                  v{p.version ?? 1} · {p.plan_id.substring(0, 8)} ({p.status})
                </option>
              ))
            )}
          </select>

          <button
            onClick={handleRunVerification}
            disabled={isRunning || !selectedPlanId}
            className="px-4 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:opacity-90 text-slate-950 font-bold font-mono text-xs rounded flex items-center gap-1.5 shadow transition disabled:opacity-40"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{isRunning ? 'Verifying...' : 'Run Verification'}</span>
          </button>
        </div>
      </div>

      {!verification ? (
        <div className="bg-noc-surface border border-noc-border rounded-lg p-10 text-center space-y-2 font-mono">
          <CheckCircle2 className="w-8 h-8 text-slate-600 mx-auto" />
          <div className="text-sm font-bold text-slate-200">No Counterfactual Verification Run Selected</div>
          <div className="text-xs text-slate-400 max-w-lg mx-auto">
            {plans.length === 0
              ? 'Generate an intervention plan in Prediction & Plans first, then select it here and click "Run Verification".'
              : 'Select a plan above and click "Run Verification" to simulate matched-seed Baseline vs. Intervention rollouts.'}
          </div>
        </div>
      ) : (
        <>
          {/* Side-by-Side Counterfactual Cards */}
          <div className="grid grid-cols-12 gap-5">
            {/* Branch A: No-Action Baseline */}
            <div className="col-span-6 bg-noc-surface border border-noc-border rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-noc-border">
                <div>
                  <div className="text-sm font-bold text-slate-200">Branch A: No-Action Baseline</div>
                  <div className="text-[10px] font-mono text-slate-500">Unmitigated Event Surge Progression</div>
                </div>
                <Badge type="CRITICAL" label="UNMITIGATED" />
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div className="p-3 bg-red-950/20 border border-red-800/40 rounded flex items-center justify-between">
                  <div>
                    <span className="text-slate-400 text-[10px] block">CONGESTED CELL MINUTES:</span>
                    <span className="text-xl font-bold text-red-400">
                      {base!.congested_cell_minutes.toFixed(1)} min
                    </span>
                  </div>
                  <AlertTriangle className="w-6 h-6 text-red-500" />
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">PEAK UTILISATION:</span>
                    <span className="text-slate-200 font-bold text-sm">
                      {base!.peak_utilisation_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">P95 LATENCY:</span>
                    <span className="text-slate-200 font-bold text-sm">
                      {base!.simulated_latency_p95_ms.toFixed(1)} ms
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">UNSERVED DEMAND:</span>
                    <span className="text-red-400 font-bold text-sm">
                      {base!.total_unserved_mbps.toFixed(1)} Mbps
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">ENERGY UNITS:</span>
                    <span className="text-slate-300 font-bold text-sm">
                      {base!.total_energy_units.toFixed(1)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Branch B: Approved Intervention */}
            <div className="col-span-6 bg-noc-surface border border-noc-border rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-noc-border">
                <div>
                  <div className="text-sm font-bold text-slate-200">Branch B: NeuralGrid Intervention</div>
                  <div className="text-[10px] font-mono text-slate-500">
                    {intv!.action_count} Plan Actions · Seed {verification.seed}
                  </div>
                </div>
                <Badge type="LOW" label="OPTIMIZED" />
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div className="p-3 bg-emerald-950/20 border border-emerald-800/40 rounded flex items-center justify-between">
                  <div>
                    <span className="text-slate-400 text-[10px] block">CONGESTED CELL MINUTES:</span>
                    <span className="text-xl font-bold text-emerald-400">
                      {intv!.congested_cell_minutes.toFixed(1)} min
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-emerald-400 font-bold flex items-center gap-1 text-sm">
                      <TrendingDown className="w-4 h-4" />
                      <span>
                        {congestedSaved >= 0 ? `-${congestedSaved}` : `+${Math.abs(congestedSaved)}`} min ({congestedSaved >= 0 ? `-${congestedPct}%` : `+${Math.abs(Number(congestedPct))}%`})
                      </span>
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">PEAK UTILISATION:</span>
                    <span className="text-emerald-300 font-bold text-sm">
                      {intv!.peak_utilisation_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">P95 LATENCY:</span>
                    <span className="text-emerald-300 font-bold text-sm">
                      {intv!.simulated_latency_p95_ms.toFixed(1)} ms
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">UNSERVED DEMAND:</span>
                    <span className="text-emerald-400 font-bold text-sm">
                      {intv!.total_unserved_mbps.toFixed(1)} Mbps
                    </span>
                  </div>
                  <div className="bg-noc-card/70 p-2.5 rounded border border-noc-border">
                    <span className="text-slate-500 text-[10px] block">ENERGY UNITS:</span>
                    <span className="text-slate-300 font-bold text-sm">
                      {intv!.total_energy_units.toFixed(1)} ({Number(energyDeltaPct) >= 0 ? `+${energyDeltaPct}%` : `${energyDeltaPct}%`})
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* TwinNode Distributed Compute Verification Panel */}
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-emerald-400" />
                <span className="font-semibold text-slate-200">TwinNode Physical Workload Execution Metrics</span>
              </div>
              <Badge type="PHYSICAL_HOST" />
            </div>

            <div className="grid grid-cols-4 gap-3">
              <div className="bg-noc-card/60 p-2.5 rounded border border-noc-border">
                <span className="text-slate-500 text-[10px] block">TASKS DISPATCHED:</span>
                <span className="text-slate-200 font-bold">
                  {verification.twinnode_metrics.tasks_total} tasks
                </span>
              </div>
              <div className="bg-noc-card/60 p-2.5 rounded border border-noc-border">
                <span className="text-slate-500 text-[10px] block">TASKS COMPLETED:</span>
                <span className="text-emerald-400 font-bold">
                  {verification.twinnode_metrics.tasks_completed} / {verification.twinnode_metrics.tasks_total}
                </span>
              </div>
              <div className="bg-noc-card/60 p-2.5 rounded border border-noc-border">
                <span className="text-slate-500 text-[10px] block">AVG COMPUTE TIME:</span>
                <span className="text-slate-200 font-bold">
                  {verification.twinnode_metrics.avg_duration_ms.toFixed(1)} ms
                </span>
              </div>
              <div className="bg-noc-card/60 p-2.5 rounded border border-noc-border">
                <span className="text-slate-500 text-[10px] block">EXECUTED NODES:</span>
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  {verification.twinnode_metrics.executed_nodes.length > 0
                    ? verification.twinnode_metrics.executed_nodes.join(', ')
                    : 'LOCAL CONTROLLER'}
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      <div className="p-3 bg-noc-card/50 border border-noc-border rounded text-[10px] font-mono text-slate-400 text-center">
        Disclaimer: Results represent a deterministic simulation counterfactual on a 100-cell synthetic network, not live Nokia base station handover.
      </div>
    </div>
  );
};
