import React, { useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  ExternalLink,
  FileText,
  Filter,
  Globe,
  MapPin,
  RefreshCw,
  Rss,
  Search,
  Sparkles,
  Users,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import { EventImpactResponse, EventRecord, EventSourceRecord } from '../types/api';

interface EventSenseProps {
  events: EventRecord[];
  selectedEvent: EventRecord | null;
  onSelectEvent: (event: EventRecord) => void;
  onRefreshEvents: () => void;
  activeSimulationId: string | null;
}

export const EventSense: React.FC<EventSenseProps> = ({
  events,
  selectedEvent,
  onSelectEvent,
  onRefreshEvents,
  activeSimulationId,
}) => {
  const [sources, setSources] = useState<EventSourceRecord[]>([]);
  const [isLoadingSources, setIsLoadingSources] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isMappingImpact, setIsMappingImpact] = useState(false);
  const [impactResult, setImpactResult] = useState<EventImpactResponse | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Load sources when an event is selected
  React.useEffect(() => {
    if (selectedEvent) {
      setIsLoadingSources(true);
      api
        .getSources(undefined, selectedEvent.event_id)
        .then((srcs) => {
          setSources(srcs);
          setIsLoadingSources(false);
        })
        .catch(() => {
          setIsLoadingSources(false);
        });
    }
  }, [selectedEvent]);

  // Handle Discover Events
  const handleDiscover = async () => {
    setIsDiscovering(true);
    setActionMessage('Running bounded discovery across GDELT DOC 2.0 & RSS feeds...');
    try {
      const res = await api.discoverEvents('Bengaluru', ['concert', 'festival', 'Palace Grounds']);
      setActionMessage(`Discovery finished: ${res.status}. Sourced ${res.source_ids?.length || 0} candidates.`);
      onRefreshEvents();
    } catch (err: any) {
      setActionMessage(`Discovery notice: ${err.message}`);
    } finally {
      setIsDiscovering(false);
    }
  };

  // Handle Crawl Sources
  const handleCrawl = async () => {
    if (!selectedEvent || sources.length === 0) return;
    setIsCrawling(true);
    setActionMessage('Executing Crawl4AI public page fetch (robots checking enabled, max 5 pages)...');
    try {
      const runId = sources[0].discovery_run_id;
      const sids = sources.slice(0, 5).map((s) => s.source_id);
      await api.crawlSources(runId, sids);
      setActionMessage('Crawl completed. Schema.org Event fields extracted.');
      onRefreshEvents();
      const updated = await api.getSources(undefined, selectedEvent.event_id);
      setSources(updated);
    } catch (err: any) {
      setActionMessage(`Crawl notice: ${err.message}`);
    } finally {
      setIsCrawling(false);
    }
  };

  // Handle Confirm Event
  const handleConfirm = async () => {
    if (!selectedEvent) return;
    setIsConfirming(true);
    try {
      await api.confirmEvent(selectedEvent.event_id, 'operator-1', true, {
        lat: selectedEvent.latitude || 13.0067,
        lon: selectedEvent.longitude || 77.5855,
      });
      setActionMessage('Event confirmed by operator. Ready for network impact mapping.');
      onRefreshEvents();
    } catch (err: any) {
      setActionMessage(`Confirmation failed: ${err.message}`);
    } finally {
      setIsConfirming(false);
    }
  };

  // Handle Map Impact
  const handleMapImpact = async () => {
    if (!selectedEvent || !activeSimulationId) {
      setActionMessage('Active simulation ID required to map impact to digital twin.');
      return;
    }
    setIsMappingImpact(true);
    try {
      const imp = await api.mapEventImpact(selectedEvent.event_id, activeSimulationId, 3.0);
      setImpactResult(imp);
      setActionMessage(`Impact successfully mapped to ${imp.affected_cells.length} cells in digital twin.`);
    } catch (err: any) {
      setActionMessage(`Impact mapping notice: ${err.message}`);
    } finally {
      setIsMappingImpact(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Provider Ingestion Status Chips */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Globe className="w-4 h-4 text-noc-cyan" />
            <div>
              <div className="text-xs font-semibold text-slate-200">GDELT DOC 2.0</div>
              <div className="text-[10px] text-slate-400 font-mono">News Discovery via Bounded HTTPX</div>
            </div>
          </div>
          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-950 border border-emerald-700/60 text-emerald-400">
            ONLINE
          </span>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Rss className="w-4 h-4 text-noc-amber" />
            <div>
              <div className="text-xs font-semibold text-slate-200">RSS / ATOM METADATA</div>
              <div className="text-[10px] text-slate-400 font-mono">Configured Feeds via Feedparser</div>
            </div>
          </div>
          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-cyan-950 border border-cyan-700/60 text-cyan-300">
            ACTIVE
          </span>
        </div>

        <div className="bg-noc-surface border border-noc-border rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <FileText className="w-4 h-4 text-noc-teal" />
            <div>
              <div className="text-xs font-semibold text-slate-200">CRAWL4AI PUBLIC PAGE</div>
              <div className="text-[10px] text-slate-400 font-mono">Schema.org JSON-LD (Robots Enabled)</div>
            </div>
          </div>
          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-950 border border-emerald-700/60 text-emerald-400">
            READY
          </span>
        </div>
      </div>

      {/* Action Notification Banner */}
      {actionMessage && (
        <div className="p-2.5 bg-noc-card border border-noc-border rounded text-xs font-mono text-noc-cyan flex items-center justify-between">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage(null)} className="text-slate-400 hover:text-slate-200 text-xs">
            ✕
          </button>
        </div>
      )}

      {/* Main Split-Screen Workspace */}
      <div className="grid grid-cols-12 gap-5">
        {/* Left Column: Discovered / Seeded Events List */}
        <div className="col-span-4 bg-noc-surface border border-noc-border rounded-lg flex flex-col h-[650px] overflow-hidden">
          <div className="p-3 border-b border-noc-border flex items-center justify-between bg-noc-card/40">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-noc-cyan" />
              <span className="text-xs font-semibold text-slate-200">Events ({events.length})</span>
            </div>
            <button
              onClick={handleDiscover}
              disabled={isDiscovering}
              className="flex items-center gap-1 px-2.5 py-1 bg-noc-cyan/20 hover:bg-noc-cyan/30 border border-noc-cyan/50 text-[11px] font-mono font-medium text-noc-cyan rounded transition disabled:opacity-50"
            >
              <Search className={`w-3 h-3 ${isDiscovering ? 'animate-spin' : ''}`} />
              <span>Discover</span>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {events.map((ev) => {
              const isSelected = selectedEvent?.event_id === ev.event_id;
              return (
                <div
                  key={ev.event_id}
                  onClick={() => onSelectEvent(ev)}
                  className={`p-3 rounded-md border cursor-pointer transition ${
                    isSelected
                      ? 'bg-noc-card border-noc-cyan/70 shadow-sm'
                      : 'bg-noc-surface hover:bg-noc-hover border-noc-border/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-bold text-slate-100 line-clamp-1">{ev.name}</span>
                    <Badge type="PUBLIC_SOURCE" label={ev.verification_status} />
                  </div>
                  <div className="text-[11px] text-noc-cyan font-mono mt-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3 text-noc-cyan flex-shrink-0" />
                    <span className="truncate">{ev.venue_name || 'Palace Grounds'}</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-slate-400">
                    <span>Origin: {ev.event_origin}</span>
                    <span>Status: {ev.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Center Column: Selected Event Profile & Source Evidence */}
        <div className="col-span-5 bg-noc-surface border border-noc-border rounded-lg flex flex-col h-[650px] overflow-hidden">
          <div className="p-3 border-b border-noc-border flex items-center justify-between bg-noc-card/40">
            <span className="text-xs font-semibold text-slate-200">Event Details & Source Evidence</span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCrawl}
                disabled={isCrawling || sources.length === 0}
                className="px-2.5 py-1 bg-noc-card hover:bg-noc-hover border border-noc-border text-[11px] font-mono text-slate-200 rounded transition disabled:opacity-40"
              >
                {isCrawling ? 'Crawling...' : 'Crawl Sources'}
              </button>
              <button
                onClick={handleConfirm}
                disabled={isConfirming || selectedEvent?.status === 'CONFIRMED'}
                className="px-2.5 py-1 bg-emerald-950 hover:bg-emerald-900 border border-emerald-600/60 text-[11px] font-mono text-emerald-300 rounded transition disabled:opacity-40"
              >
                {selectedEvent?.status === 'CONFIRMED' ? 'Confirmed ✓' : 'Confirm Event'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {selectedEvent ? (
              <>
                <div>
                  <h3 className="text-base font-bold text-slate-100">{selectedEvent.name}</h3>
                  <div className="text-xs text-noc-cyan font-mono mt-1 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5" />
                    <span>{selectedEvent.venue_name || 'Palace Grounds, Bengaluru'}</span>
                  </div>
                </div>

                {/* Evidence Metadata Grid */}
                <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-noc-card/60 p-3 rounded border border-noc-border">
                  <div>
                    <span className="text-slate-500 text-[10px] block">VENUE COORDINATES:</span>
                    <span className="text-slate-200">
                      {selectedEvent.latitude ? `${selectedEvent.latitude.toFixed(4)}° N, ${selectedEvent.longitude?.toFixed(4)}° E` : '13.0067° N, 77.5855° E'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[10px] block">ATTENDANCE BASIS:</span>
                    <span className="text-purple-300 font-semibold">{selectedEvent.attendance_basis}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[10px] block">ATTENDANCE RANGE:</span>
                    <span className="text-slate-200">
                      {selectedEvent.attendance_low || 15000} - {selectedEvent.attendance_high || 25000}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[10px] block">INTENSITY MULTIPLIER:</span>
                    <span className="text-noc-cyan font-semibold">{selectedEvent.intensity.toFixed(1)}x Surge</span>
                  </div>
                </div>

                {/* Source Evidence List */}
                <div>
                  <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
                    <span>Captured Public Source Records ({sources.length})</span>
                    <span className="text-[10px] font-mono text-slate-500">GDELT / Crawl4AI</span>
                  </div>

                  {isLoadingSources ? (
                    <div className="text-xs text-slate-500 font-mono py-4 text-center">Loading sources...</div>
                  ) : sources.length === 0 ? (
                    <div className="p-3 bg-noc-bg/60 border border-noc-border rounded text-xs text-slate-400 font-mono">
                      No live external crawl records. Using seeded Palace Grounds demonstration scenario.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {sources.map((src) => (
                        <div key={src.source_id} className="p-2.5 rounded bg-noc-card border border-noc-border text-xs font-mono">
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span className="text-noc-cyan font-semibold">{src.domain}</span>
                            <span>{src.fetch_status}</span>
                          </div>
                          <div className="font-medium text-slate-200 mt-1 line-clamp-1">{src.title || src.url}</div>
                          {src.evidence_summary && (
                            <div className="text-[11px] text-slate-400 mt-1 italic line-clamp-2">
                              "{src.evidence_summary}"
                            </div>
                          )}
                          <div className="mt-2 flex items-center justify-between text-[9px] text-slate-500">
                            <span>Extractor: {src.fetch_provider || 'pending'}</span>
                            <span className="truncate max-w-[150px]">{src.url}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="p-3 bg-noc-bg/60 border border-noc-border rounded text-[10px] font-mono text-slate-400 leading-relaxed">
                  <span className="text-noc-cyan font-bold">Epistemic Rule:</span> External mentions are attention signals.
                  Attendance is calibrated strictly against venue capacities or explicit operator assumptions.
                </div>
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono">
                Select an event from the left list.
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Geographic Network Impact Preview */}
        <div className="col-span-3 bg-noc-surface border border-noc-border rounded-lg flex flex-col h-[650px] overflow-hidden">
          <div className="p-3 border-b border-noc-border flex items-center justify-between bg-noc-card/40">
            <span className="text-xs font-semibold text-slate-200">Cell Impact Preview</span>
            <button
              onClick={handleMapImpact}
              disabled={isMappingImpact || !selectedEvent}
              className="px-2.5 py-1 bg-noc-cyan/20 hover:bg-noc-cyan/30 border border-noc-cyan/50 text-[11px] font-mono font-medium text-noc-cyan rounded transition disabled:opacity-40"
            >
              {isMappingImpact ? 'Mapping...' : 'Map to Twin'}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {impactResult ? (
              <>
                <div className="p-2.5 bg-noc-card rounded border border-noc-border text-xs font-mono">
                  <div className="text-slate-400 text-[10px]">TOTAL UPLIFT:</div>
                  <div className="text-xl font-bold text-noc-cyan mt-0.5">
                    +{impactResult.total_estimated_uplift_mbps.toFixed(0)} Mbps
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1">
                    Radius: {impactResult.influence_radius_km} km | Scenario: {impactResult.attendance_scenario}
                  </div>
                </div>

                <div className="text-xs font-semibold text-slate-300">
                  Affected Cells ({impactResult.affected_cells.length})
                </div>

                <div className="space-y-1.5 max-h-[420px] overflow-y-auto">
                  {impactResult.affected_cells.map((ac) => (
                    <div
                      key={ac.cell_id}
                      className="p-2 bg-noc-card/70 border border-noc-border rounded text-xs font-mono flex items-center justify-between"
                    >
                      <div>
                        <div className="font-semibold text-slate-200">{ac.cell_id}</div>
                        <div className="text-[10px] text-slate-400">{ac.distance_km.toFixed(2)} km away</div>
                      </div>
                      <div className="text-right">
                        <span className="text-purple-300 font-bold">
                          +{ac.estimated_additional_demand_mbps.toFixed(0)} Mbps
                        </span>
                        <div className="text-[9px] text-slate-500">Weight: {ac.impact_weight.toFixed(2)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-4 text-slate-500 font-mono text-xs">
                <Compass className="w-8 h-8 text-slate-600 mb-2" />
                <span>Confirm event and click "Map to Twin" to calculate cell impact.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
