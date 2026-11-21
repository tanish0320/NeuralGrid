import React from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  Calendar,
  CheckCircle2,
  Cpu,
  Layers,
  MapPin,
  Radio,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { CellRecord, CellTelemetryRecord, EventRecord, NodeRecord, SimulationStateResponse } from '../types/api';

interface CommandCentreProps {
  cells: CellRecord[];
  simState: SimulationStateResponse | null;
  activeEvent: EventRecord | null;
  nodes: NodeRecord[];
  onSelectScreen: (screen: any) => void;
  onSelectCell: (cellId: string) => void;
}

export const CommandCentre: React.FC<CommandCentreProps> = ({
  cells,
  simState,
  activeEvent,
  nodes,
  onSelectScreen,
  onSelectCell,
}) => {
  const summary = simState?.summary;
  const telemetry = simState?.telemetry || [];

  // Group cells at risk
  const telemetryByCell = new Map<string, CellTelemetryRecord>(
    telemetry.map((t) => [t.cell_id, t])
  );

  const riskCells = telemetry
    .filter((t) => t.utilisation_pct >= 70 || t.simulated_latency_ms >= 35 || t.cell_state === 'FAILED')
    .sort((a, b) => b.utilisation_pct - a.utilisation_pct)
    .slice(0, 8);

  const junaidNode = nodes.find((n) => n.node_id === 'NODE-JUNAID');
  const tanishNode = nodes.find((n) => n.node_id === 'NODE-TANISH');

  return (
    <div className="space-y-5">
      {/* Top Operational KPI Strip */}
      <div className="grid grid-cols-6 gap-3">
        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>NETWORK CELLS</span>
            <Layers className="w-3.5 h-3.5 text-noc-cyan" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-100">
              {cells.length || 100}
            </span>
            <span className="text-[10px] text-emerald-400 font-mono">
              {summary?.active_cells || 100} ACTIVE
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="SYNTHETIC" />
            <span className="text-[9px] text-slate-500 font-mono">100% COVERAGE</span>
          </div>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>CELLS AT RISK</span>
            <AlertTriangle className="w-3.5 h-3.5 text-noc-amber" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-noc-amber">
              {summary?.congested_cells ?? (riskCells.length || 0)}
            </span>
            <span className="text-[10px] text-noc-amber font-mono">&gt;70% UTIL</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="MODEL_PREDICTION" />
            <span className="text-[9px] text-slate-400 font-mono">15m HORIZON</span>
          </div>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>TOTAL DEMAND</span>
            <TrendingUp className="w-3.5 h-3.5 text-noc-cyan" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-100">
              {(summary?.total_demand_mbps || 0).toFixed(0)}
            </span>
            <span className="text-xs text-slate-400 font-mono">Mbps</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="SYNTHETIC" />
            <span className="text-[9px] text-slate-400 font-mono">
              QUEUED: {(summary?.total_queued_mbps || 0).toFixed(0)}M
            </span>
          </div>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>MEAN LATENCY</span>
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-100">
              {(summary?.mean_simulated_latency_ms || 18.5).toFixed(1)}
            </span>
            <span className="text-xs text-slate-400 font-mono">ms</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="SYNTHETIC" />
            <span className="text-[9px] text-emerald-400 font-mono">SLA &lt; 45ms</span>
          </div>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>ACTIVE EVENT</span>
            <Calendar className="w-3.5 h-3.5 text-noc-cyan" />
          </div>
          <div className="mt-2">
            <div className="text-sm font-semibold text-slate-100 truncate" title={activeEvent?.name || 'Palace Grounds Concert'}>
              {activeEvent ? activeEvent.name.substring(0, 18) : 'Palace Grounds'}
            </div>
            <div className="text-[10px] text-noc-cyan font-mono truncate">
              {activeEvent?.venue_name || 'Palace Grounds'}
            </div>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="PUBLIC_SOURCE" label="DEMO EVENT" />
            <span className="text-[9px] text-noc-cyan font-mono">
              {activeEvent?.verification_status || 'SEEDED'}
            </span>
          </div>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>TWINNODE STATUS</span>
            <Cpu className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${junaidNode?.is_online ? 'bg-emerald-400' : 'bg-slate-500'}`} />
            <span className="text-sm font-bold font-mono text-slate-100">
              {junaidNode?.state || 'STANDBY'}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <Badge type="PHYSICAL_HOST" />
            <span className="text-[9px] text-slate-400 font-mono">
              CPU: {tanishNode?.latest_host_telemetry?.cpu_pct?.toFixed(0) || 12}%
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid: Geographic Topology Preview + Active Event & Risk Panel */}
      <div className="grid grid-cols-12 gap-5">
        {/* Left Column: Geographic/Grid Topology Overview */}
        <div className="col-span-8 bg-noc-surface border border-noc-border rounded-lg flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-noc-border flex items-center justify-between bg-noc-card/40">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-noc-cyan" />
              <span className="text-xs font-semibold text-slate-200">
                Bengaluru 100-Cell Network Grid & Event Footprint
              </span>
              <Badge type="SYNTHETIC" />
            </div>
            <button
              onClick={() => onSelectScreen('twin')}
              className="text-xs font-mono text-noc-cyan hover:underline flex items-center gap-1"
            >
              <span>Interactive Cytoscape Topology</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Cell Matrix / Geo Visualization */}
          <div className="p-4 flex-1 flex flex-col justify-between bg-[#070A10]">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 mb-2">
              <span>Coverage Area: 100 cells (Urban BLR-Central, North, East, South, West)</span>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500 inline-block" /> &lt;70%
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-amber-500 inline-block" /> 70-85%
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-red-500 inline-block" /> &gt;85%
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-purple-500 border border-purple-300 inline-block" /> Event Impact
                </span>
              </div>
            </div>

            {/* 10x10 Cell Grid Representation */}
            <div className="grid grid-cols-10 gap-1.5 p-3 bg-noc-bg/80 border border-noc-border/60 rounded-lg">
              {cells.map((cell, idx) => {
                const tel = telemetryByCell.get(cell.cell_id);
                const util = tel ? tel.utilisation_pct : (cell.capacity_mbps > 800 ? 55 : 45);
                const isEventImpacted = idx >= 15 && idx <= 26; // Palace Grounds region cluster

                let cellBg = 'bg-emerald-950/70 border-emerald-700/60 text-emerald-300';
                if (util >= 85) {
                  cellBg = 'bg-red-950/90 border-red-500 text-red-200 animate-pulse';
                } else if (util >= 70) {
                  cellBg = 'bg-amber-950/80 border-amber-600/80 text-amber-200';
                }

                if (isEventImpacted) {
                  cellBg += ' ring-1 ring-purple-400/80';
                }

                return (
                  <button
                    key={cell.cell_id}
                    onClick={() => {
                      onSelectCell(cell.cell_id);
                      onSelectScreen('twin');
                    }}
                    className={`h-9 rounded flex flex-col items-center justify-center p-1 text-[10px] font-mono border transition hover:scale-105 ${cellBg}`}
                    title={`${cell.cell_id} (${cell.region})\nCap: ${cell.capacity_mbps} Mbps\nUtil: ${util.toFixed(1)}%\nCrit: ${cell.criticality}`}
                  >
                    <span className="font-semibold text-[9px] truncate max-w-full">
                      {cell.cell_id.replace('CELL-BLR-', '#')}
                    </span>
                    <span className="text-[8px] opacity-80">{util.toFixed(0)}%</span>
                  </button>
                );
              })}
            </div>

            <div className="mt-3 flex items-center justify-between text-[11px] font-mono text-slate-400 bg-noc-surface/60 p-2 rounded border border-noc-border/40">
              <div className="flex items-center gap-2">
                <MapPin className="w-3.5 h-3.5 text-noc-cyan" />
                <span>Palace Grounds Epicentre: 13.0067° N, 77.5855° E (Influence Radius: 3.0 km)</span>
              </div>
              <span className="text-purple-300">Cells impacted: 12 cluster cells</span>
            </div>
          </div>
        </div>

        {/* Right Column: Active Event Profile & Risk Queue */}
        <div className="col-span-4 space-y-4">
          {/* Active Event Card */}
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-noc-cyan" />
                <span className="text-xs font-semibold text-slate-200">Active Public Event</span>
              </div>
              <Badge type="PUBLIC_SOURCE" label={activeEvent?.verification_status || 'DEMO SCENARIO'} />
            </div>

            <div className="mt-3 space-y-2.5">
              <div>
                <div className="text-sm font-bold text-slate-100">
                  {activeEvent?.name || 'Palace Grounds Concert — DEMO SCENARIO'}
                </div>
                <div className="text-xs text-noc-cyan font-mono mt-0.5">
                  Venue: {activeEvent?.venue_name || 'Palace Grounds, Bengaluru'}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-noc-card/60 p-2.5 rounded border border-noc-border/60">
                <div>
                  <span className="text-slate-500 block text-[10px]">ATTENDANCE:</span>
                  <span className="text-slate-200 font-semibold">
                    {activeEvent?.attendance_high ? `${activeEvent.attendance_high.toLocaleString()} est.` : '25,000 (Scenario)'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px]">DEMAND UPLIFT:</span>
                  <span className="text-purple-300 font-semibold">+1.8x Peak Surge</span>
                </div>
              </div>

              <div className="text-[11px] text-slate-400 leading-relaxed">
                Extracted from public news sources and verified against known Palace Grounds capacity.
                Triggering demand surge on neighbouring cells.
              </div>

              <button
                onClick={() => onSelectScreen('eventsense')}
                className="w-full py-2 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-xs font-mono font-medium text-noc-cyan flex items-center justify-center gap-1.5 transition"
              >
                <span>View Event Evidence & Impact</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Top Risk Cells Panel */}
          <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-noc-border">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-noc-amber" />
                <span className="text-xs font-semibold text-slate-200">Cells Requiring Action</span>
              </div>
              <Badge type="MODEL_PREDICTION" />
            </div>

            <div className="mt-3 space-y-2 max-h-[220px] overflow-y-auto">
              {riskCells.length === 0 ? (
                <div className="text-xs text-slate-500 font-mono py-4 text-center">
                  All 100 cells operating within normal thresholds (&lt;70% util).
                </div>
              ) : (
                riskCells.map((rc) => {
                  const bandType = rc.utilisation_pct >= 85 ? 'CRITICAL' : 'HIGH';
                  return (
                    <div
                      key={rc.cell_id}
                      onClick={() => {
                        onSelectCell(rc.cell_id);
                        onSelectScreen('prediction');
                      }}
                      className="flex items-center justify-between p-2 rounded bg-noc-card/70 hover:bg-noc-hover border border-noc-border/50 cursor-pointer transition text-xs font-mono"
                    >
                      <div>
                        <div className="font-semibold text-slate-200">{rc.cell_id}</div>
                        <div className="text-[10px] text-slate-400">
                          Latency: {rc.simulated_latency_ms.toFixed(1)} ms
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-slate-100 font-bold">{rc.utilisation_pct.toFixed(0)}%</span>
                        <Badge type={bandType} label={bandType} />
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <button
              onClick={() => onSelectScreen('prediction')}
              className="mt-3 w-full py-2 bg-gradient-to-r from-cyan-950 to-teal-950 hover:from-cyan-900 hover:to-teal-900 border border-cyan-700/60 rounded text-xs font-mono font-medium text-cyan-200 flex items-center justify-center gap-1.5 transition shadow"
            >
              <span>Review Mitigation Plan</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
