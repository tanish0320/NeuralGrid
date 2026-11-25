import React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  Cpu,
  ExternalLink,
  Info,
  Layers,
  MapPin,
  Radio,
  ShieldCheck,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import { Badge } from './common/Badge';
import { MitigatingTower, SurgeJustification, SurgeTower } from '../types/api';

interface LoadSplittingJustificationPanelProps {
  surgeTower: SurgeTower | null;
  mitigatingTowers: MitigatingTower[];
  justification: SurgeJustification | null;
  className?: string;
  onSelectTower?: (cellId: string) => void;
}

export const LoadSplittingJustificationPanel: React.FC<LoadSplittingJustificationPanelProps> = ({
  surgeTower,
  mitigatingTowers,
  justification,
  className = '',
  onSelectTower,
}) => {
  if (!surgeTower || !justification || !justification.traffic_breakdown || !justification.hard_constraints) {
    return (
      <div className={`bg-noc-surface border border-noc-border rounded-lg p-6 text-center ${className}`}>
        <Radio className="w-8 h-8 text-slate-500 mx-auto mb-2 animate-pulse" />
        <h4 className="text-sm font-mono text-slate-300 font-bold">Awaiting Real-Time Surge Scan</h4>
        <p className="text-xs text-slate-500 font-mono mt-1 max-w-md mx-auto">
          Trigger a real-time Bengaluru scan to parse live RSS feeds, detect crowd gatherings, identify overloaded cell towers, and calculate load-splitting justification.
        </p>
      </div>
    );
  }

  const tb = justification.traffic_breakdown;
  const hc = justification.hard_constraints;

  return (
    <div className={`bg-noc-surface border border-noc-border rounded-lg p-5 space-y-5 ${className}`}>
      {/* 1. Header: Locality, Reason & Real-Time Provenance */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-noc-border">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold text-red-400 bg-red-950/80 px-2 py-0.5 rounded border border-red-700/60 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              PREDICTED CELLULAR SURGE & LOAD-SPLITTING DISPATCH
            </span>
            <Badge type="PUBLIC_SOURCE" label="REAL-TIME SCRAPED" />
            <Badge type="SYNTHETIC" label="GEO LOCALIZED" />
          </div>

          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2 mt-1">
            <MapPin className="w-4 h-4 text-noc-cyan flex-shrink-0" />
            <span>{justification.locality}</span>
          </h3>

          <p className="text-xs text-slate-300 font-mono">
            <strong>Spike Reason:</strong> {justification.spike_reason}
          </p>
        </div>

        {/* Event Time & Live Source Citation */}
        <div className="flex flex-col sm:flex-row lg:flex-col items-start lg:items-end gap-1.5 text-xs font-mono">
          <div className="flex items-center gap-1.5 text-noc-amber bg-noc-bg px-2.5 py-1 rounded border border-noc-border">
            <Clock className="w-3.5 h-3.5" />
            <span>{justification.event_window}</span>
          </div>

          <a
            href={justification.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-noc-cyan hover:underline bg-noc-bg px-2.5 py-1 rounded border border-noc-border group"
          >
            <span>Source: {justification.source_citation}</span>
            <ExternalLink className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
          </a>
        </div>
      </div>

      {/* 2. Numerical Traffic Breakdown Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="bg-noc-bg border border-noc-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
            <span>EST. ATTENDEES</span>
            <Users className="w-3.5 h-3.5 text-noc-cyan" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">
            ~{justification.estimated_attendees.toLocaleString()}
          </div>
          <div className="text-[9px] font-mono text-slate-400 mt-1">VENUE CAPACITY RANGE</div>
        </div>

        <div className="bg-noc-bg border border-noc-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
            <span>BASE DEMAND</span>
            <Layers className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">
            {tb.base_demand_mbps} <span className="text-xs text-slate-400">Mbps</span>
          </div>
          <div className="text-[9px] font-mono text-emerald-400 mt-1">TYPICAL CBD BASELINE</div>
        </div>

        <div className="bg-noc-bg border border-noc-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
            <span>SURGE UPLIFT</span>
            <TrendingUp className="w-3.5 h-3.5 text-noc-amber" />
          </div>
          <div className="text-xl font-bold font-mono text-noc-amber mt-1">
            +{tb.surge_uplift_mbps} <span className="text-xs text-slate-400">Mbps</span>
          </div>
          <div className="text-[9px] font-mono text-noc-amber mt-1">1.55 Mbps / 100 ATT</div>
        </div>

        <div className="bg-noc-bg border border-noc-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
            <span>SURGE TOWER CAP</span>
            <Radio className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">
            {tb.tower_capacity_mbps} <span className="text-xs text-slate-400">Mbps</span>
          </div>
          <div className="text-[9px] font-mono text-slate-400 mt-1">TOWER {surgeTower.cell_id}</div>
        </div>

        <div className="bg-red-950/40 border border-red-800/80 rounded-lg p-3">
          <div className="text-[10px] font-mono text-red-300 flex items-center justify-between">
            <span>UNMITIGATED LOAD</span>
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
          </div>
          <div className="text-xl font-bold font-mono text-red-400 mt-1">
            {tb.total_unmitigated_demand_mbps} <span className="text-xs text-slate-400">Mbps</span>
          </div>
          <div className="text-[9px] font-mono text-red-300 font-bold mt-1">
            {tb.overload_pct}% OVERLOAD DEFICIT
          </div>
        </div>

        <div className="bg-cyan-950/40 border border-cyan-700/80 rounded-lg p-3">
          <div className="text-[10px] font-mono text-cyan-300 flex items-center justify-between">
            <span>LOAD OFFLOADED</span>
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold font-mono text-cyan-300 mt-1">
            {tb.total_offloaded_mbps} <span className="text-xs text-slate-400">Mbps</span>
          </div>
          <div className="text-[9px] font-mono text-emerald-400 font-bold mt-1">
            TO {mitigatingTowers.length} MITIGATING TOWERS
          </div>
        </div>
      </div>

      {/* 3. Mitigating Towers Table: Headroom and Load Redistribution */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-mono font-bold text-slate-200 flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-noc-cyan" />
            <span>MITIGATING TOWERS (DONOR HEADROOM & OFF-LOAD ALLOCATION)</span>
          </h4>
          <span className="text-[10px] font-mono text-slate-400">
            LOAD SPLITTING VIA CO-SITED HANDOVER VECTORS
          </span>
        </div>

        <div className="border border-noc-border rounded-lg overflow-x-auto bg-noc-bg">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-noc-surface border-b border-noc-border text-slate-400 text-[10px] uppercase">
              <tr>
                <th className="py-2.5 px-3">Donor Tower ID</th>
                <th className="py-2.5 px-3">Locality / Sector</th>
                <th className="py-2.5 px-3">Distance</th>
                <th className="py-2.5 px-3">Capacity</th>
                <th className="py-2.5 px-3">Headroom Before</th>
                <th className="py-2.5 px-3 text-noc-cyan">Offload Allocated</th>
                <th className="py-2.5 px-3">Headroom After</th>
                <th className="py-2.5 px-3">Post-Mitigation Util</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-noc-border text-slate-200">
              {mitigatingTowers.map((donor) => (
                <tr
                  key={donor.cell_id}
                  onClick={() => onSelectTower && onSelectTower(donor.cell_id)}
                  className="hover:bg-noc-surface/60 transition-colors cursor-pointer group"
                >
                  <td className="py-2.5 px-3 font-bold text-noc-cyan flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 group-hover:scale-125 transition-transform" />
                    <span>{donor.cell_id}</span>
                  </td>
                  <td className="py-2.5 px-3 text-slate-300">{donor.locality}</td>
                  <td className="py-2.5 px-3 text-slate-400">{donor.distance_km} km</td>
                  <td className="py-2.5 px-3 text-slate-300">{donor.capacity_mbps} Mbps</td>
                  <td className="py-2.5 px-3 text-slate-400">{donor.headroom_before_mbps} Mbps</td>
                  <td className="py-2.5 px-3 font-bold text-noc-cyan bg-cyan-950/30">
                    +{donor.offload_allocated_mbps} Mbps
                  </td>
                  <td className="py-2.5 px-3 text-emerald-400">{donor.headroom_after_mbps} Mbps</td>
                  <td className="py-2.5 px-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 border border-emerald-700/60 text-emerald-300">
                      {donor.util_after_pct}% (&lt; 78% SLA)
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. Engineering Hard Constraints & Justification */}
      <div className="bg-noc-bg border border-noc-border rounded-lg p-4 space-y-2">
        <div className="flex items-center gap-2 text-xs font-mono font-bold text-slate-200">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>HARD-CONSTRAINT VERIFICATION & LOAD-SPLITTING JUSTIFICATION</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono pt-1">
          <div className="flex items-start gap-2 bg-noc-surface/80 p-2.5 rounded border border-noc-border">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-slate-200">Fiber Backhaul Headroom Margin</div>
              <div className="text-slate-400 text-[11px] mt-0.5">{hc.backhaul_margin}</div>
            </div>
          </div>

          <div className="flex items-start gap-2 bg-noc-surface/80 p-2.5 rounded border border-noc-border">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-slate-200">Edge Latency SLA Protection</div>
              <div className="text-slate-400 text-[11px] mt-0.5">{hc.latency_sla}</div>
            </div>
          </div>

          <div className="flex items-start gap-2 bg-noc-surface/80 p-2.5 rounded border border-noc-border">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-slate-200">Session Continuity & Handover Churn</div>
              <div className="text-slate-400 text-[11px] mt-0.5">{hc.handover_churn}</div>
            </div>
          </div>

          <div className="flex items-start gap-2 bg-noc-surface/80 p-2.5 rounded border border-noc-border">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-slate-200">Standby Booster Cell Provisioning</div>
              <div className="text-slate-400 text-[11px] mt-0.5">{hc.standby_activation}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
