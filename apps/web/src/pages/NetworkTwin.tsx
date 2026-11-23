import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Compass,
  Filter,
  Layers,
  MapPin,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  Wrench,
  Zap,
  RefreshCw,
  Activity,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { BangaloreGeoMap } from '../components/BangaloreGeoMap';
import { api } from '../services/api';
import {
  CellImpactAggregated,
  CellOverlapSummary,
  CellRecord,
  CellTelemetryRecord,
  GraphResponse,
  ImpactRecalculateResponse,
  LoadDistributionVector,
  MitigatingTower,
  SimulationStateResponse,
  SurgeTower,
} from '../types/api';

interface NetworkTwinProps {
  cells: CellRecord[];
  graphData: GraphResponse | null;
  simState: SimulationStateResponse | null;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  onRefreshSimulation: () => void;
}

export const NetworkTwin: React.FC<NetworkTwinProps> = ({
  cells,
  graphData,
  simState,
  selectedCellId,
  onSelectCell,
  onRefreshSimulation,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  const [regionFilter, setRegionFilter] = useState<string>('ALL');
  const [isPlaying, setIsPlaying] = useState<boolean>(simState?.status === 'RUNNING');
  const [isStepping, setIsStepping] = useState<boolean>(false);
  const [faultCellId, setFaultCellId] = useState<string>('CELL-BLR-018');
  const [showFaultModal, setShowFaultModal] = useState<boolean>(false);
  const [viewFormat, setViewFormat] = useState<'GEOMAP' | 'CYTOSCAPE'>('GEOMAP');
  const [surgeTower, setSurgeTower] = useState<SurgeTower | null>(null);
  const [mitigatingTowers, setMitigatingTowers] = useState<MitigatingTower[]>([]);
  const [loadVectors, setLoadVectors] = useState<LoadDistributionVector[]>([]);

  // Phase 5: Geospatial Impact Assessment state
  const [cellImpacts, setCellImpacts] = useState<CellImpactAggregated[]>([]);
  const [cellOverlaps, setCellOverlaps] = useState<CellOverlapSummary[]>([]);
  const [selectedCellImpact, setSelectedCellImpact] = useState<CellImpactAggregated | null>(null);
  const [isRecalculating, setIsRecalculating] = useState<boolean>(false);
  const [recalcSummary, setRecalcSummary] = useState<ImpactRecalculateResponse | null>(null);

  const loadImpactData = () => {
    api.getCellImpacts().then(setCellImpacts).catch(() => {});
    api.getImpactOverlaps().then(setCellOverlaps).catch(() => {});
  };

  useEffect(() => {
    loadImpactData();
  }, []);

  useEffect(() => {
    if (selectedCellId) {
      api.getCellImpactDetail(selectedCellId).then(setSelectedCellImpact).catch(() => setSelectedCellImpact(null));
    } else {
      setSelectedCellImpact(null);
    }
  }, [selectedCellId]);

  const handleRecalculateImpacts = async () => {
    setIsRecalculating(true);
    try {
      const res = await api.recalculateImpacts();
      setRecalcSummary(res);
      loadImpactData();
      if (selectedCellId) {
        api.getCellImpactDetail(selectedCellId).then(setSelectedCellImpact).catch(() => {});
      }
    } catch (err) {
      console.error('Impact recalculation failed:', err);
    } finally {
      setIsRecalculating(false);
    }
  };

  useEffect(() => {
    api
      .realtimeScan('Bengaluru', false, simState?.simulation_id)
      .then((res) => {
        if (res.surge_tower) {
          setSurgeTower(res.surge_tower);
          setMitigatingTowers(res.mitigating_towers);
          setLoadVectors(res.load_distribution);
        }
      })
      .catch(() => {});
  }, [simState?.simulation_id]);

  const safeCells = Array.isArray(cells) ? cells : [];
  const selectedCell = safeCells.find((c) => c.cell_id === selectedCellId);
  const safeTelemetry = Array.isArray(simState?.telemetry) ? simState.telemetry : [];
  const selectedTelemetry = safeTelemetry.find((t) => t.cell_id === selectedCellId);

  // Initialize Cytoscape
  useEffect(() => {
    const safeNodes = Array.isArray(graphData?.nodes) ? graphData.nodes : [];
    const safeEdges = Array.isArray(graphData?.edges) ? graphData.edges : [];
    if (!containerRef.current || safeNodes.length === 0) return;

    const elements: cytoscape.ElementDefinition[] = [];

    // Nodes
    safeNodes.forEach((n, idx) => {
      const id = n.id || n.cell_id || `CELL-${idx}`;
      const label = n.label || id.replace('CELL-BLR-', '#');
      // Deterministic synthetic coordinate layout
      const col = idx % 10;
      const row = Math.floor(idx / 10);
      elements.push({
        group: 'nodes',
        data: {
          id,
          label,
          region: n.region,
          criticality: n.criticality,
          capacity: n.capacity || n.capacity_mbps || 500,
        },
        position: {
          x: 100 + col * 90 + (row % 2 ? 45 : 0),
          y: 80 + row * 80,
        },
      });
    });

    // Edges
    safeEdges.forEach((e, idx) => {
      const id = e.id || e.edge_id || `EDGE-${idx}`;
      const source = e.source || e.source_cell_id;
      const target = e.target || e.target_cell_id;
      const type = e.type || e.edge_type || 'PRIMARY_NEIGHBOR';
      if (source && target) {
        elements.push({
          group: 'edges',
          data: {
            id,
            source,
            target,
            type,
          },
        });
      }
    });

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#10B981',
            label: 'data(label)',
            color: '#F8FAFC',
            'font-family': 'ui-monospace, monospace',
            'font-size': '10px',
            'font-weight': 'bold',
            'text-valign': 'center',
            'text-halign': 'center',
            width: 38,
            height: 38,
            'border-width': 2,
            'border-color': '#064E3B',
          },
        },
        {
          selector: 'node.moderate',
          style: {
            'background-color': '#F59E0B',
            'border-color': '#78350F',
          },
        },
        {
          selector: 'node.critical',
          style: {
            'background-color': '#EF4444',
            'border-color': '#7F1D1D',
          },
        },
        {
          selector: 'node.selected',
          style: {
            'border-color': '#06B6D4',
            'border-width': 4,
            width: 44,
            height: 44,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#1F293D',
            'curve-style': 'straight',
            opacity: 0.7,
          },
        },
        {
          selector: 'edge[type = "BACKHAUL_CLUSTER"]',
          style: {
            'line-color': '#0891B2',
            width: 2,
            'line-style': 'dashed',
          },
        },
        {
          selector: 'edge.highlighted',
          style: {
            'line-color': '#06B6D4',
            width: 3,
            opacity: 1,
          },
        },
      ],
      layout: { name: 'preset' },
      minZoom: 0.4,
      maxZoom: 3.0,
      wheelSensitivity: 0.2,
    });

    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      onSelectCell(node.id());
    });

    cyRef.current = cy;
    cy.fit(undefined, 30);

    return () => {
      cy.destroy();
    };
  }, [graphData]);

  // Update Cytoscape styles dynamically as telemetry changes
  useEffect(() => {
    if (!cyRef.current || !simState) return;
    const cy = cyRef.current;

    const telList = simState.telemetry || [];
    const telMap = new Map<string, CellTelemetryRecord>(
      telList.map((t) => [t.cell_id, t])
    );

    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const id = n.id();
        const tel = telMap.get(id);
        n.removeClass('moderate critical selected');

        if (tel) {
          if (tel.cell_state === 'FAILED' || tel.utilisation_pct >= 85) {
            n.addClass('critical');
          } else if (tel.utilisation_pct >= 70) {
            n.addClass('moderate');
          }
        }

        if (id === selectedCellId) {
          n.addClass('selected');
        }
      });

      // Highlight edges connecting to selected node
      cy.edges().removeClass('highlighted');
      if (selectedCellId) {
        cy.edges(`[source = "${selectedCellId}"], [target = "${selectedCellId}"]`).addClass('highlighted');
      }
    });
  }, [simState, selectedCellId]);

  // Handle Play/Pause
  const handleTogglePlay = async () => {
    if (!simState) return;
    try {
      if (isPlaying) {
        await api.pauseSimulation(simState.simulation_id);
        setIsPlaying(false);
      } else {
        await api.resumeSimulation(simState.simulation_id);
        setIsPlaying(true);
      }
      onRefreshSimulation();
    } catch (_) {}
  };

  // Handle Step (+5m tick)
  const handleStep = async () => {
    if (!simState || isStepping) return;
    setIsStepping(true);
    try {
      await api.stepSimulation(simState.simulation_id, 1);
      onRefreshSimulation();
    } finally {
      setIsStepping(false);
    }
  };

  // Handle Fault Injection
  const handleInjectFault = async () => {
    if (!simState) return;
    try {
      await api.injectFault(simState.simulation_id, faultCellId, 'CELL_FAILURE', 1.0);
      setShowFaultModal(false);
      onRefreshSimulation();
    } catch (_) {}
  };

  return (
    <div className="flex flex-col h-[750px] space-y-3">
      {/* Top Topology Controls Bar */}
      <div className="bg-noc-surface border border-noc-border rounded-lg px-4 py-2.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Layers className="w-4 h-4 text-noc-cyan" />
          <span className="text-xs font-semibold text-slate-200">100-Cell Network Digital Twin</span>
          <Badge type="SYNTHETIC" />
          <div className="h-4 w-px bg-noc-border" />
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
            <span>Average Degree: {graphData?.average_degree || 5.2} neighbours/cell</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View Format Selector */}
          <div className="flex bg-noc-bg rounded p-0.5 border border-noc-border font-mono text-xs">
            <button
              onClick={() => setViewFormat('GEOMAP')}
              className={`px-2.5 py-1 rounded text-[11px] font-bold flex items-center gap-1 transition-colors ${
                viewFormat === 'GEOMAP'
                  ? 'bg-noc-cyan text-noc-bg'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Compass className="w-3 h-3" />
              <span>Bangalore NOC Map</span>
            </button>
            <button
              onClick={() => setViewFormat('CYTOSCAPE')}
              className={`px-2.5 py-1 rounded text-[11px] font-bold flex items-center gap-1 transition-colors ${
                viewFormat === 'CYTOSCAPE'
                  ? 'bg-noc-cyan text-noc-bg'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3 h-3" />
              <span>Cytoscape Graph</span>
            </button>
          </div>

          {viewFormat === 'CYTOSCAPE' && (
            <button
              onClick={() => cyRef.current?.fit(undefined, 30)}
              className="px-2.5 py-1 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-[11px] font-mono text-slate-300 flex items-center gap-1"
            >
              <Maximize2 className="w-3 h-3" />
              <span>Fit View</span>
            </button>
          )}

          <button
            onClick={handleRecalculateImpacts}
            disabled={isRecalculating}
            className="px-2.5 py-1 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-[11px] font-mono text-noc-cyan flex items-center gap-1 disabled:opacity-50"
            title="Recalculate multi-source canonical event impacts across 100-cell network"
          >
            <RefreshCw className={`w-3 h-3 ${isRecalculating ? 'animate-spin' : ''}`} />
            <span>{isRecalculating ? 'Recalculating...' : 'Recalc Impacts'}</span>
          </button>

          <button
            onClick={() => setShowFaultModal(true)}
            className="px-2.5 py-1 bg-red-950/70 hover:bg-red-900 border border-red-700/60 rounded text-[11px] font-mono text-red-300 flex items-center gap-1"
          >
            <AlertOctagon className="w-3 h-3" />
            <span>Inject Fault</span>
          </button>
        </div>
      </div>

      {recalcSummary && (
        <div className="bg-noc-card/90 border border-noc-cyan/40 px-3 py-1.5 rounded flex items-center justify-between text-[11px] font-mono text-noc-cyan">
          <span>
            Impact Recalculation Complete: {recalcSummary.mapped_events_count} events mapped across {recalcSummary.affected_cells_count} cells ({recalcSummary.overlapping_cells_count} overlapping concurrency zones). Max Surge: {recalcSummary.max_cell_demand_delta_mbps} Mbps.
          </span>
          <button onClick={() => setRecalcSummary(null)} className="text-slate-400 hover:text-slate-200">✕</button>
        </div>
      )}

      {/* Main Graph Viewport + Selected Cell Drawer */}
      <div className="flex-1 grid grid-cols-12 gap-3 min-h-0">
        {/* Viewport: Geo Map or Cytoscape Container */}
        <div className="col-span-8 bg-[#070A10] border border-noc-border rounded-lg relative overflow-hidden flex flex-col">
          {viewFormat === 'GEOMAP' ? (
            <BangaloreGeoMap
              cells={cells}
              surgeTower={surgeTower}
              mitigatingTowers={mitigatingTowers}
              loadVectors={loadVectors}
              cellImpacts={cellImpacts}
              cellOverlaps={cellOverlaps}
              venueLocation={
                surgeTower
                  ? {
                      lat: surgeTower.lat,
                      lon: surgeTower.lon,
                      name: surgeTower.locality || 'Bengaluru Event Venue',
                    }
                  : null
              }
              selectedCellId={selectedCellId}
              onSelectCell={onSelectCell}
              className="h-full border-0 rounded-none"
            />
          ) : (
            <>
              <div ref={containerRef} className="w-full h-full" />
              <div className="absolute bottom-3 left-3 bg-noc-card/90 border border-noc-border px-3 py-1.5 rounded text-[10px] font-mono text-slate-400 pointer-events-none">
                Click any cell node to inspect telemetry, queueing, and neighbours.
              </div>
            </>
          )}
        </div>

        {/* Selected Cell Detail Drawer */}
        <div className="col-span-4 bg-noc-surface border border-noc-border rounded-lg p-4 flex flex-col justify-between overflow-y-auto">
          {selectedCell ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-noc-border">
                <div>
                  <h3 className="text-base font-bold font-mono text-slate-100">{selectedCell.cell_id}</h3>
                  <span className="text-[11px] text-noc-cyan font-mono">{selectedCell.region} Region</span>
                </div>
                <Badge
                  type={
                    selectedTelemetry?.utilisation_pct && selectedTelemetry.utilisation_pct >= 85
                      ? 'CRITICAL'
                      : selectedTelemetry?.utilisation_pct && selectedTelemetry.utilisation_pct >= 70
                      ? 'HIGH'
                      : 'LOW'
                  }
                />
              </div>

              {/* Operational Metrics */}
              <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-noc-card/70 p-3 rounded border border-noc-border">
                <div>
                  <span className="text-slate-500 text-[10px] block">CAPACITY:</span>
                  <span className="text-slate-200 font-semibold">{selectedCell.capacity_mbps} Mbps</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">CRITICALITY:</span>
                  <span className="text-slate-200 font-semibold">{selectedCell.criticality}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">CURRENT DEMAND:</span>
                  <span className="text-slate-100 font-bold">
                    {(selectedTelemetry?.demand_mbps ?? 0).toFixed(1)} Mbps
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">UTILISATION:</span>
                  <span
                    className={`font-bold ${
                      selectedTelemetry?.utilisation_pct && selectedTelemetry.utilisation_pct >= 85
                        ? 'text-red-400'
                        : selectedTelemetry?.utilisation_pct && selectedTelemetry.utilisation_pct >= 70
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {(selectedTelemetry?.utilisation_pct ?? 0).toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">SERVED TRAFFIC:</span>
                  <span className="text-emerald-400">
                    {(selectedTelemetry?.served_mbps ?? 0).toFixed(1)} Mbps
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">QUEUED BACKLOG:</span>
                  <span
                    className={
                      selectedTelemetry?.queued_mbps && selectedTelemetry.queued_mbps > 0
                        ? 'text-amber-400 font-bold'
                        : 'text-slate-400'
                    }
                  >
                    {(selectedTelemetry?.queued_mbps ?? 0).toFixed(1)} Mbps
                  </span>
                </div>
              </div>

              {/* Latency & Quality Breakdown */}
              <div className="bg-noc-card/70 p-3 rounded border border-noc-border text-xs font-mono space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Simulated Latency:</span>
                  <span className="text-slate-200 font-bold">
                    {(selectedTelemetry?.simulated_latency_ms ?? (selectedCell as any)?.base_latency_ms ?? 15.0).toFixed(1)} ms
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Unserved Drop:</span>
                  <span className="text-red-400 font-bold">
                    {(selectedTelemetry?.unserved_mbps ?? 0).toFixed(1)} Mbps
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Operational State:</span>
                  <span className="text-noc-cyan font-semibold">
                    {selectedTelemetry?.cell_state || selectedCell?.current_state || selectedCell?.initial_state || 'ACTIVE'}
                  </span>
                </div>
              </div>

              {/* Phase 5: Geospatial Impact Assessment */}
              {selectedCellImpact && selectedCellImpact.contributing_event_count > 0 && (
                <div className="bg-noc-card/90 border border-noc-cyan/40 p-3 rounded space-y-2.5">
                  <div className="flex items-center justify-between pb-2 border-b border-noc-border">
                    <span className="text-[11px] font-mono font-bold text-noc-cyan flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5" />
                      EVENT IMPACT ASSESSMENT
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold ${
                        selectedCellImpact.congestion_risk_band === 'CRITICAL'
                          ? 'bg-red-950 text-red-300 border border-red-700'
                          : selectedCellImpact.congestion_risk_band === 'HIGH'
                          ? 'bg-amber-950 text-amber-300 border border-amber-700'
                          : selectedCellImpact.congestion_risk_band === 'ELEVATED'
                          ? 'bg-yellow-950 text-yellow-300 border border-yellow-700'
                          : 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                      }`}
                    >
                      {selectedCellImpact.congestion_risk_band} RISK
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                    <div>
                      <span className="text-slate-500 block text-[9px]">PREDICTED SURGE:</span>
                      <span className="text-noc-cyan font-bold">+{selectedCellImpact.combined_demand_delta_mbps.toFixed(1)} Mbps</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[9px]">PROJECTED UTIL:</span>
                      <span className="text-slate-200 font-bold">{selectedCellImpact.projected_utilisation_pct.toFixed(1)}%</span>
                    </div>
                  </div>

                  {selectedCellImpact.contributing_event_count > 1 && (
                    <div className="p-2 bg-amber-950/40 border border-amber-700/50 rounded text-[10px] font-mono text-amber-300">
                      <span className="font-bold">Multi-Event Overlap Detected:</span> {selectedCellImpact.contributing_event_count} simultaneous events affecting cell. Sub-linear device saturation applied.
                    </div>
                  )}

                  <div className="space-y-1.5 pt-1">
                    <span className="text-[10px] font-mono text-slate-400 block font-semibold">
                      CONTRIBUTING EVENTS ({selectedCellImpact.contributing_events.length}):
                    </span>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {selectedCellImpact.contributing_events.map((ev, idx) => (
                        <div key={idx} className="p-2 bg-noc-bg/80 border border-noc-border rounded text-[10px] font-mono space-y-1">
                          <div className="flex justify-between items-start">
                            <span className="text-slate-200 font-bold truncate max-w-[170px]" title={ev.event_title}>
                              {ev.event_title}
                            </span>
                            <span className="text-noc-cyan font-semibold">+{ev.demand_delta_mbps.toFixed(1)}M</span>
                          </div>
                          <div className="flex justify-between text-slate-400 text-[9px]">
                            <span>{ev.event_category} • {ev.distance_km.toFixed(2)} km</span>
                            <span className="text-slate-500">Conf: {(ev.impact_confidence * 100).toFixed(0)}%</span>
                          </div>
                          {ev.venue_name && (
                            <div className="text-[9px] text-slate-400 truncate">
                              Venue: {ev.venue_name}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Invariant Truth Notice */}
              <div className="p-2.5 bg-noc-bg/60 border border-noc-border rounded text-[10px] font-mono text-slate-400">
                <span className="text-noc-cyan font-bold">Mass Balance Invariant:</span>{' '}
                demand ({(selectedTelemetry?.demand_mbps ?? 0).toFixed(0)}M) = served ({(selectedTelemetry?.served_mbps ?? 0).toFixed(0)}M) + queued ({(selectedTelemetry?.queued_mbps ?? 0).toFixed(0)}M) + unserved ({(selectedTelemetry?.unserved_mbps ?? 0).toFixed(0)}M)
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono text-center">
              Select a cell from the topology graph to inspect live metrics.
            </div>
          )}

          <div className="pt-3 border-t border-noc-border text-[10px] font-mono text-slate-500">
            Coordinates: {selectedCell ? `${(selectedCell.latitude ?? selectedCell.lat ?? 12.9716).toFixed(4)}° N, ${(selectedCell.longitude ?? selectedCell.lon ?? 77.5946).toFixed(4)}° E` : '—'}
          </div>
        </div>
      </div>

      {/* Bottom 5-Minute Simulation Tick Scrubber Bar */}
      <div className="bg-noc-surface border border-noc-border rounded-lg px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={handleTogglePlay}
            className={`px-3 py-1.5 rounded text-xs font-mono font-bold flex items-center gap-1.5 transition ${
              isPlaying
                ? 'bg-amber-950 border border-amber-600 text-amber-300'
                : 'bg-emerald-950 border border-emerald-600 text-emerald-300'
            }`}
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPlaying ? 'Pause' : 'Play Simulation'}</span>
          </button>

          <button
            onClick={handleStep}
            disabled={isStepping || isPlaying}
            className="px-3 py-1.5 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-xs font-mono text-slate-200 flex items-center gap-1.5 disabled:opacity-40"
          >
            <SkipForward className="w-3.5 h-3.5 text-noc-cyan" />
            <span>Step +5m Tick</span>
          </button>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono text-slate-300">
          <div>
            <span className="text-slate-500">STATE VERSION:</span> {simState?.state_version || 0}
          </div>
          <div className="h-4 w-px bg-noc-border" />
          <div>
            <span className="text-slate-500">SIMULATED TIME:</span> {simState?.sim_time_utc?.substring(0, 19).replace('T', ' ') || '2026-11-21 12:00:00'} UTC
          </div>
        </div>
      </div>

      {/* Fault Injection Modal */}
      {showFaultModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-noc-surface border border-noc-border rounded-lg p-5 w-96 space-y-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-noc-border">
              <span className="text-sm font-bold text-red-400 flex items-center gap-2">
                <AlertOctagon className="w-4 h-4" /> Inject Cellular Fault
              </span>
              <button onClick={() => setShowFaultModal(false)} className="text-slate-400 hover:text-slate-200">
                ✕
              </button>
            </div>
            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="text-slate-400 block mb-1">Target Cell ID:</label>
                <input
                  type="text"
                  value={faultCellId}
                  onChange={(e) => setFaultCellId(e.target.value)}
                  className="w-full bg-noc-card border border-noc-border rounded px-2.5 py-1.5 text-slate-100 font-mono"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Fault Type:</label>
                <select className="w-full bg-noc-card border border-noc-border rounded px-2.5 py-1.5 text-slate-100 font-mono">
                  <option value="CELL_FAILURE">CELL_FAILURE (Hard Outage)</option>
                  <option value="BACKHAUL_CONGESTION">BACKHAUL_CONGESTION (High RTT)</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-noc-border">
              <button
                onClick={() => setShowFaultModal(false)}
                className="px-3 py-1.5 bg-noc-card border border-noc-border text-xs font-mono text-slate-300 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleInjectFault}
                className="px-3 py-1.5 bg-red-950 border border-red-600 text-xs font-mono font-bold text-red-300 rounded"
              >
                Execute Fault
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
