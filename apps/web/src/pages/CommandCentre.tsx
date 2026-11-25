import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  Globe,
  Layers,
  MapPin,
  Radio,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { BangaloreGeoMap } from '../components/BangaloreGeoMap';
import { LoadSplittingJustificationPanel } from '../components/LoadSplittingJustificationPanel';
import { api } from '../services/api';
import {
  CellRecord,
  CellTelemetryRecord,
  EventRecord,
  LoadDistributionVector,
  MitigatingTower,
  NodeRecord,
  RealtimeScanResponse,
  SimulationStateResponse,
  SurgeJustification,
  SurgeTower,
} from '../types/api';

interface CommandCentreProps {
  cells: CellRecord[];
  simState: SimulationStateResponse | null;
  activeEvent: EventRecord | null;
  nodes: NodeRecord[];
  onSelectScreen: (screen: any) => void;
  onSelectCell: (cellId: string) => void;
  onRefreshSimulation?: () => void;
  onRefreshEvents?: () => void;
}

export const CommandCentre: React.FC<CommandCentreProps> = ({
  cells,
  simState,
  activeEvent,
  nodes,
  onSelectScreen,
  onSelectCell,
  onRefreshSimulation,
  onRefreshEvents,
}) => {
  const summary = simState?.summary;
  const telemetry = simState?.telemetry || [];

  const [viewMode, setViewMode] = useState<'MAP' | 'GRID'>('MAP');
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [surgeTower, setSurgeTower] = useState<SurgeTower | null>(null);
  const [mitigatingTowers, setMitigatingTowers] = useState<MitigatingTower[]>([]);
  const [loadVectors, setLoadVectors] = useState<LoadDistributionVector[]>([]);
  const [justification, setJustification] = useState<SurgeJustification | null>(null);
  const [discoveredEvents, setDiscoveredEvents] = useState<EventRecord[]>([]);

  // Execute real-time scan across live Bengaluru RSS feeds
  const handleRealtimeScan = async () => {
    setIsScanning(true);
    setScanMessage('Scanning real-time Bengaluru news & RSS feeds for crowd gatherings...');
    try {
      const res = await api.realtimeScan('Bengaluru', true, simState?.simulation_id);
      if (res.surge_tower) {
        setSurgeTower(res.surge_tower);
        setMitigatingTowers(res.mitigating_towers);
        setLoadVectors(res.load_distribution);
        setJustification(res.justification);
        setDiscoveredEvents(res.events);
        setScanMessage(
          `Discovered ${res.events.length} live Bengaluru events. Epicenter identified at ${res.surge_tower.locality} (${res.surge_tower.cell_id}).`
        );
      }
      onRefreshSimulation?.();
      onRefreshEvents?.();
    } catch (err: any) {
      setScanMessage(`Real-time scan notice: ${err.message}`);
    } finally {
      setIsScanning(false);
    }
  };

  // Run lightweight read-only preview on mount once simState is ready (full live crawl on explicit button click)
  useEffect(() => {
    if (!surgeTower && simState?.simulation_id) {
      api
        .realtimeScan('Bengaluru', false, simState.simulation_id)
        .then((res) => {
          if (res.surge_tower) {
            setSurgeTower(res.surge_tower);
            setMitigatingTowers(res.mitigating_towers);
            setLoadVectors(res.load_distribution);
            setJustification(res.justification);
            setDiscoveredEvents(res.events);
            setScanMessage(
              `Loaded ${res.events.length} Bengaluru events (${res.discovered_sources_count} scraped sources). Epicenter: ${res.surge_tower.locality} (${res.surge_tower.cell_id}).`
            );
          }
        })
        .catch(() => {});
    }
  }, [simState?.simulation_id]);

  // Group cells at risk
  const telemetryByCell = new Map<string, CellTelemetryRecord>(
    telemetry.map((t) => [t.cell_id, t])
  );

  const riskCells = telemetry
    .filter((t) => t.utilisation_pct >= 70 || t.simulated_latency_ms >= 35 || t.cell_state === 'FAILED')
    .sort((a, b) => b.utilisation_pct - a.utilisation_pct)
    .slice(0, 8);

  const safeNodes = Array.isArray(nodes) ? nodes : [];
  const junaidNode = safeNodes.find((n) => n.node_id === 'NODE-JUNAID');
  const tanishNode = safeNodes.find((n) => n.node_id === 'NODE-TANISH');

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

      {/* Real-Time Live Scraper & Surge Prediction Control Banner */}
      <div className="bg-gradient-to-r from-noc-surface via-noc-card to-noc-surface border border-noc-cyan/40 rounded-lg p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-[0_0_20px_rgba(6,182,212,0.1)]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
            <span className="text-xs font-mono font-bold text-noc-cyan tracking-wider">
              REAL-TIME BENGALURU EVENT SCRAPER & CELLULAR SURGE PREDICTOR
            </span>
            <Badge type="PUBLIC_SOURCE" label="LIVE RSS STREAM" />
            <Badge type="SYNTHETIC" label="AI GEOCODER" />
          </div>
          <p className="text-xs font-mono text-slate-300">
            {scanMessage ||
              'Scrapes live Bengaluru news & ticket feeds, geocodes crowd venue coordinates, detects cell tower overload, and plans load-splitting.'}
          </p>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs w-full md:w-auto justify-end">
          {/* View Mode Toggle */}
          <div className="flex bg-noc-bg rounded p-0.5 border border-noc-border">
            <button
              onClick={() => setViewMode('MAP')}
              className={`px-3 py-1.5 rounded text-[11px] font-bold flex items-center gap-1.5 transition-colors ${
                viewMode === 'MAP'
                  ? 'bg-noc-cyan text-noc-bg'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Bangalore NOC Map</span>
            </button>
            <button
              onClick={() => setViewMode('GRID')}
              className={`px-3 py-1.5 rounded text-[11px] font-bold flex items-center gap-1.5 transition-colors ${
                viewMode === 'GRID'
                  ? 'bg-noc-cyan text-noc-bg'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>10x10 Grid</span>
            </button>
          </div>

          {/* Trigger Scan Button */}
          <button
            onClick={handleRealtimeScan}
            disabled={isScanning}
            className="px-3.5 py-1.5 bg-red-950 border border-red-500 hover:bg-red-900 text-red-200 rounded text-xs font-bold font-mono flex items-center gap-2 transition disabled:opacity-50 shadow-[0_0_12px_rgba(239,68,68,0.3)]"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-red-400 ${isScanning ? 'animate-spin' : ''}`} />
            <span>{isScanning ? 'Scraping Live...' : 'Run Real-Time Scan'}</span>
          </button>
        </div>
      </div>

      {/* Main Geographic Topology or Abstract Grid */}
      {viewMode === 'MAP' ? (
        <div className="space-y-5">
          <div className="grid grid-cols-12 gap-5">
            {/* Left 8-col: Bangalore Leaflet Map */}
            <div className="col-span-8">
              <BangaloreGeoMap
                cells={cells}
                surgeTower={surgeTower}
                mitigatingTowers={mitigatingTowers}
                loadVectors={loadVectors}
                venueLocation={
                  surgeTower
                    ? {
                        lat: surgeTower.lat,
                        lon: surgeTower.lon,
                        name: justification?.locality || 'Bengaluru Event Venue',
                      }
                    : null
                }
                selectedCellId={simState?.telemetry?.[0]?.cell_id || null}
                onSelectCell={onSelectCell}
              />
            </div>

            {/* Right 4-col: Live Event Profile & Top Risk Cells */}
            <div className="col-span-4 space-y-4">
              {/* Active Scraped Event Card */}
              <div className="bg-noc-surface border border-noc-border rounded-lg p-4">
                <div className="flex items-center justify-between pb-3 border-b border-noc-border">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-noc-cyan" />
                    <span className="text-xs font-semibold text-slate-200">Real-Time Extracted Event</span>
                  </div>
                  <Badge type="PUBLIC_SOURCE" label="SCRAPED TODAY" />
                </div>

                <div className="mt-3 space-y-2.5">
                  <div>
                    <div className="text-sm font-bold text-slate-100">
                      {justification?.spike_reason || activeEvent?.name || 'Palace Grounds Jatre & Concert'}
                    </div>
                    <div className="text-xs text-noc-cyan font-mono mt-0.5">
                      Locality: {justification?.locality || 'Palace Grounds (Jayamahal / Sadashivanagar)'}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-noc-card/60 p-2.5 rounded border border-noc-border/60">
                    <div>
                      <span className="text-slate-500 block text-[10px]">EST. ATTENDANCE:</span>
                      <span className="text-slate-200 font-semibold">
                        ~{(justification?.estimated_attendees || 32000).toLocaleString()}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">PEAK UPLIFT:</span>
                      <span className="text-purple-300 font-semibold">
                        +{justification?.traffic_breakdown?.surge_uplift_mbps ?? 580} Mbps
                      </span>
                    </div>
                  </div>

                  <div className="text-[11px] text-slate-400 leading-relaxed font-mono">
                    Scraped from live RSS feeds and geocoded directly to Bengaluru cell cluster. Triggers automatic load redistribution to neighboring donor towers.
                  </div>

                  <button
                    onClick={() => onSelectScreen('eventsense')}
                    className="w-full py-2 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-xs font-mono font-medium text-noc-cyan flex items-center justify-center gap-1.5 transition"
                  >
                    <span>Inspect Raw Evidence & Articles</span>
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

                <div className="mt-3 space-y-2 max-h-[190px] overflow-y-auto">
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
                              Latency: {(rc.simulated_latency_ms ?? 15.0).toFixed(1)} ms
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-slate-100 font-bold">{(rc.utilisation_pct ?? 50.0).toFixed(0)}%</span>
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

          {/* Full-Width Load-Splitting Justification Panel */}
          <LoadSplittingJustificationPanel
            surgeTower={surgeTower}
            mitigatingTowers={mitigatingTowers}
            justification={justification}
            onSelectTower={(cid) => {
              onSelectCell(cid);
              onSelectScreen('twin');
            }}
          />
        </div>
      ) : (
        /* Abstract 10x10 Matrix Grid View */
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
                {cells.map((cell) => {
                  const tel = telemetryByCell.get(cell.cell_id);
                  const util = typeof tel?.utilisation_pct === 'number' ? tel.utilisation_pct : (cell.capacity_mbps > 800 ? 55 : 45);
                  const isEventImpacted = (tel?.event_demand_mbps ?? 0) > 0 || cell.cell_id === surgeTower?.cell_id;

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
                  <span>
                    {activeEvent?.venue_name || justification?.locality || 'Palace Grounds'} Epicentre:{' '}
                    {(activeEvent?.latitude ?? surgeTower?.lat ?? 13.0067).toFixed(4)}° N,{' '}
                    {(activeEvent?.longitude ?? surgeTower?.lon ?? 77.5855).toFixed(4)}° E (Radius: 3.0 km)
                  </span>
                </div>
                <span className="text-purple-300">
                  Cells impacted: {telemetry.filter((t) => t.event_demand_mbps > 0 || t.cell_id === surgeTower?.cell_id).length} cluster cells
                </span>
              </div>
            </div>
          </div>

          {/* Right Column: Active Event Profile & Risk Queue */}
          <div className="col-span-4 space-y-4">
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
                            Latency: {(rc.simulated_latency_ms ?? 15.0).toFixed(1)} ms
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-100 font-bold">{(rc.utilisation_pct ?? 50.0).toFixed(0)}%</span>
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
      )}
    </div>
  );
};
