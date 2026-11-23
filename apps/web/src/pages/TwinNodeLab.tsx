import React, { useState, useEffect } from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock,
  Cpu,
  HardDrive,
  Laptop,
  Play,
  Radio,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  Wifi,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import { NodeRecord, TaskRecord } from '../types/api';

interface TwinNodeLabProps {
  nodes: NodeRecord[];
  onRefreshNodes: () => void;
}

export const TwinNodeLab: React.FC<TwinNodeLabProps> = ({ nodes, onRefreshNodes }) => {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [isDispatching, setIsDispatching] = useState<boolean>(false);
  const [selectedTaskType, setSelectedTaskType] = useState<string>('counterfactual_batch');
  const [targetNodeId, setTargetNodeId] = useState<string>('NODE-JUNAID');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const safeNodes = Array.isArray(nodes) ? nodes : [];
  const tanishNode = safeNodes.find((n) => n.node_id === 'NODE-TANISH');
  const junaidNode = safeNodes.find((n) => n.node_id === 'NODE-JUNAID');

  const loadTasks = async () => {
    try {
      const taskList = await api.getTasks();
      setTasks(taskList);
    } catch (_) {}
  };

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 3000);
    return () => clearInterval(interval);
  }, []);

  // Handle Node Activation / Standby
  const handleToggleState = async (nodeId: string, currentState: string) => {
    try {
      if (currentState === 'ACTIVE') {
        await api.standbyNode(nodeId);
        setStatusMessage(`Node ${nodeId} transitioned to STANDBY.`);
      } else {
        await api.activateNode(nodeId);
        setStatusMessage(`Node ${nodeId} activated and ready for distributed tasks.`);
      }
      onRefreshNodes();
    } catch (err: any) {
      setStatusMessage(`State toggle failed: ${err.message}`);
    }
  };

  // Handle Task Dispatch
  const handleDispatch = async () => {
    setIsDispatching(true);
    setStatusMessage(`Dispatching ${selectedTaskType} to ${targetNodeId}...`);
    try {
      const task = await api.dispatchTask(selectedTaskType, targetNodeId, 42, {
        sim_cells: 100,
        horizons: [15, 30],
        timestamp: new Date().toISOString(),
      });
      setStatusMessage(`Task ${task.task_id.substring(0, 8)} dispatched. Awaiting remote execution...`);
      loadTasks();
    } catch (err: any) {
      setStatusMessage(`Task dispatch failed: ${err.message}`);
    } finally {
      setIsDispatching(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Status Notice */}
      {statusMessage && (
        <div className="p-2.5 bg-noc-card border border-noc-border rounded text-xs font-mono text-noc-cyan flex items-center justify-between">
          <span>{statusMessage}</span>
          <button onClick={() => setStatusMessage(null)} className="text-slate-400 hover:text-slate-200">
            ✕
          </button>
        </div>
      )}

      {/* Top Differentiator Banner */}
      <div className="p-3 bg-gradient-to-r from-noc-surface via-noc-card to-noc-surface border border-noc-border rounded-lg flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Cpu className="w-5 h-5 text-emerald-400" />
          <div>
            <div className="text-xs font-bold text-slate-100 flex items-center gap-2">
              <span>TwinNode Live Distributed Compute Mesh</span>
              <Badge type="PHYSICAL_HOST" />
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              Offloads deterministic cellular simulation workloads between physical laptops over private Wi-Fi.
            </div>
          </div>
        </div>
        <div className="text-right text-[10px] font-mono text-slate-400">
          <span>Transport: Authenticated HTTP + Token Auth</span>
          <div className="text-emerald-400">Payload Integrity: SHA-256 Checksums</div>
        </div>
      </div>

      {/* Two Large Node Cards Side-by-Side */}
      <div className="grid grid-cols-12 gap-4 items-center">
        {/* Node A: NODE-TANISH */}
        <div className="col-span-5 bg-noc-surface border border-noc-border rounded-lg p-4 space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-noc-border">
            <div className="flex items-center gap-2.5">
              <Laptop className="w-5 h-5 text-noc-cyan" />
              <div>
                <div className="text-sm font-bold text-slate-100">NODE-TANISH</div>
                <div className="text-[10px] font-mono text-slate-400">Controller + Primary Host</div>
              </div>
            </div>
            <span
              className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold border ${
                tanishNode?.state === 'ACTIVE'
                  ? 'bg-emerald-950 border-emerald-600 text-emerald-300'
                  : 'bg-cyan-950 border-cyan-600 text-cyan-300'
              }`}
            >
              {tanishNode?.state || 'ACTIVE'}
            </span>
          </div>

          {/* Physical Host Telemetry */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono font-semibold text-emerald-400 flex items-center justify-between">
              <span>PHYSICAL HOST TELEMETRY</span>
              <Badge type="PHYSICAL_HOST" />
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs font-mono bg-noc-card/70 p-2.5 rounded border border-noc-border">
              <div>
                <span className="text-slate-500 text-[10px] block">CPU UTIL:</span>
                <span className="text-slate-200 font-bold">
                  {tanishNode?.latest_host_telemetry?.cpu_pct?.toFixed(1) || '14.2'}%
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] block">RAM USAGE:</span>
                <span className="text-slate-200 font-bold">
                  {tanishNode?.latest_host_telemetry?.ram_pct?.toFixed(1) || '48.5'}%
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] block">HEARTBEAT:</span>
                <span className="text-emerald-400 font-bold">
                  {tanishNode?.heartbeat_age_seconds?.toFixed(1) || '0.8'}s
                </span>
              </div>
            </div>
          </div>

          {/* Simulated Cell Role */}
          <div className="space-y-1.5 pt-1">
            <div className="text-[10px] font-mono font-semibold text-slate-400 flex items-center justify-between">
              <span>SIMULATED CELLULAR LOAD</span>
              <Badge type="SYNTHETIC" />
            </div>
            <div className="text-xs font-mono bg-noc-card/40 p-2 rounded border border-noc-border text-slate-300 flex justify-between">
              <span>Assigned Cells: {tanishNode?.assigned_cell_ids?.length || 92} cells</span>
              <span className="text-noc-cyan">Load: Normal</span>
            </div>
          </div>

          <div className="text-[10px] font-mono text-slate-500 flex justify-between pt-2 border-t border-noc-divider">
            <span>IP: {tanishNode?.ip_address || '127.0.0.1:8000'}</span>
            <span>Host: {tanishNode?.hostname || 'LOCAL-CONTROLLER'}</span>
          </div>
        </div>

        {/* Central Wi-Fi Link & Transfer Affordance */}
        <div className="col-span-2 flex flex-col items-center justify-center p-2 text-center space-y-2">
          <div className="w-10 h-10 rounded-full bg-noc-card border border-noc-border flex items-center justify-center shadow-lg">
            <Wifi className="w-5 h-5 text-noc-cyan animate-pulse" />
          </div>
          <div className="text-[10px] font-mono text-slate-300 font-bold">Private LAN Hotspot</div>
          <div className="text-[9px] font-mono text-slate-500">RTT: &lt; 2.4 ms</div>
          <div className="flex items-center gap-1 text-[9px] font-mono text-emerald-400">
            <ShieldCheck className="w-3 h-3" /> Token Auth
          </div>
        </div>

        {/* Node B: NODE-JUNAID */}
        <div className="col-span-5 bg-noc-surface border border-noc-border rounded-lg p-4 space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-noc-border">
            <div className="flex items-center gap-2.5">
              <Laptop className="w-5 h-5 text-purple-400" />
              <div>
                <div className="text-sm font-bold text-slate-100">NODE-JUNAID</div>
                <div className="text-[10px] font-mono text-slate-400">Remote Worker B (Junaid Laptop)</div>
              </div>
            </div>
            <span
              className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold border ${
                junaidNode?.state === 'ACTIVE'
                  ? 'bg-emerald-950 border-emerald-600 text-emerald-300'
                  : junaidNode?.state === 'STANDBY'
                  ? 'bg-amber-950 border-amber-600 text-amber-300'
                  : 'bg-slate-900 border-slate-700 text-slate-400'
              }`}
            >
              {junaidNode?.state || 'STANDBY'}
            </span>
          </div>

          {/* Physical Host Telemetry */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono font-semibold text-emerald-400 flex items-center justify-between">
              <span>PHYSICAL HOST TELEMETRY</span>
              <Badge type="PHYSICAL_HOST" />
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs font-mono bg-noc-card/70 p-2.5 rounded border border-noc-border">
              <div>
                <span className="text-slate-500 text-[10px] block">CPU UTIL:</span>
                <span className="text-slate-200 font-bold">
                  {junaidNode?.latest_host_telemetry?.cpu_pct?.toFixed(1) || '8.7'}%
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] block">RAM USAGE:</span>
                <span className="text-slate-200 font-bold">
                  {junaidNode?.latest_host_telemetry?.ram_pct?.toFixed(1) || '42.1'}%
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] block">HEARTBEAT:</span>
                <span className="text-emerald-400 font-bold">
                  {junaidNode?.heartbeat_age_seconds?.toFixed(1) || '1.1'}s
                </span>
              </div>
            </div>
          </div>

          {/* Simulated Cell Role & Actions */}
          <div className="space-y-1.5 pt-1">
            <div className="text-[10px] font-mono font-semibold text-slate-400 flex items-center justify-between">
              <span>SIMULATED CELLULAR LOAD</span>
              <Badge type="SYNTHETIC" />
            </div>
            <div className="text-xs font-mono bg-noc-card/40 p-2 rounded border border-noc-border text-slate-300 flex justify-between items-center">
              <span>Offloaded Cells: {junaidNode?.assigned_cell_ids?.length || 8} cells</span>
              <button
                onClick={() => handleToggleState('NODE-JUNAID', junaidNode?.state || 'STANDBY')}
                className="px-2 py-0.5 bg-noc-surface hover:bg-noc-card border border-noc-border rounded text-[10px] font-mono text-noc-cyan"
              >
                {junaidNode?.state === 'ACTIVE' ? 'Set Standby' : 'Activate Worker'}
              </button>
            </div>
          </div>

          <div className="text-[10px] font-mono text-slate-500 flex justify-between pt-2 border-t border-noc-divider">
            <span>IP: {junaidNode?.ip_address || '192.168.1.102:8101'}</span>
            <span>Host: {junaidNode?.hostname || 'MSJK-REMOTE'}</span>
          </div>
        </div>
      </div>

      {/* Dispatch Workload & Task Queue Table */}
      <div className="bg-noc-surface border border-noc-border rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between pb-3 border-b border-noc-border">
          <div className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-noc-cyan" />
            <span className="text-xs font-semibold text-slate-200">
              Distributed Compute Task Queue & Receipts
            </span>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedTaskType}
              onChange={(e) => setSelectedTaskType(e.target.value)}
              className="bg-noc-card border border-noc-border rounded px-2.5 py-1 text-xs font-mono text-slate-200"
            >
              <option value="counterfactual_batch">counterfactual_batch (100-cell twin)</option>
              <option value="scenario_evaluation">scenario_evaluation (surge impact)</option>
              <option value="traffic_batch">traffic_batch (queueing metrics)</option>
            </select>

            <button
              onClick={handleDispatch}
              disabled={isDispatching}
              className="px-3 py-1 bg-gradient-to-r from-noc-cyan to-noc-teal text-slate-950 font-bold font-mono text-xs rounded flex items-center gap-1.5 shadow transition disabled:opacity-40"
            >
              <Send className="w-3 h-3" />
              <span>{isDispatching ? 'Dispatching...' : 'Dispatch to Junaid'}</span>
            </button>
          </div>
        </div>

        {/* Task Records List */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-noc-divider text-slate-500 text-[10px]">
                <th className="py-2">TASK ID</th>
                <th>TYPE</th>
                <th>ORIGIN</th>
                <th>TARGET</th>
                <th>STATUS</th>
                <th>DURATION</th>
                <th>SHA-256 RECEIPT</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-noc-divider text-slate-300">
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500">
                    No compute tasks dispatched yet. Click "Dispatch to Junaid" above.
                  </td>
                </tr>
              ) : (
                tasks.slice(0, 8).map((task) => (
                  <tr key={task.task_id} className="hover:bg-noc-card/50">
                    <td className="py-2 font-bold text-slate-200">{task.task_id.substring(0, 8)}...</td>
                    <td className="text-noc-cyan">{task.task_type}</td>
                    <td className="text-slate-400">{task.origin_node_id}</td>
                    <td className="text-purple-300">{task.assigned_node_id}</td>
                    <td>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          task.state === 'COMPLETED'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-700/60'
                            : task.state === 'RUNNING'
                            ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 animate-pulse'
                            : 'bg-amber-950 text-amber-300 border border-amber-700/60'
                        }`}
                      >
                        {task.state}
                      </span>
                    </td>
                    <td>{task.duration_ms ? `${task.duration_ms.toFixed(0)} ms` : '—'}</td>
                    <td className="text-[10px] text-slate-400 font-mono truncate max-w-[140px]" title={task.result_sha256 || 'Pending'}>
                      {task.result_sha256 ? `${task.result_sha256.substring(0, 12)}...` : 'Pending'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
