import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import {
  Compass,
  Filter,
  Layers,
  MapPin,
  Maximize2,
  Radio,
  RefreshCw,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { Badge } from './common/Badge';
import { CellRecord, LoadDistributionVector, MitigatingTower, SurgeTower } from '../types/api';

interface BangaloreGeoMapProps {
  cells: CellRecord[];
  surgeTower: SurgeTower | null;
  mitigatingTowers: MitigatingTower[];
  loadVectors: LoadDistributionVector[];
  venueLocation?: { lat: number; lon: number; name: string } | null;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  className?: string;
}

export const BangaloreGeoMap: React.FC<BangaloreGeoMapProps> = ({
  cells,
  surgeTower,
  mitigatingTowers,
  loadVectors,
  venueLocation,
  selectedCellId,
  onSelectCell,
  className = '',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const vectorsLayerRef = useRef<L.LayerGroup | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  const [filterMode, setFilterMode] = useState<'ALL' | 'SURGE_ONLY' | 'CBD' | 'WHITEFIELD' | 'ECITY'>('ALL');
  const [mapStyle, setMapStyle] = useState<'GOOGLE_DARK' | 'GOOGLE_ROADMAP' | 'GOOGLE_SATELLITE'>('GOOGLE_DARK');

  // Initialize Leaflet map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Center on Bengaluru NOC coordinates
    const map = L.map(mapContainerRef.current, {
      center: [12.9716, 77.5946],
      zoom: 12,
      minZoom: 10,
      maxZoom: 20,
      zoomControl: false,
    });

    // Google Maps tile layer (worldwide direct Google raster CDN, no API key required)
    const tileLayer = L.tileLayer('https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
      maxZoom: 20,
      attribution: '&copy; Google Maps',
    }).addTo(map);

    tileLayerRef.current = tileLayer;

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    markersLayerRef.current = L.layerGroup().addTo(map);
    vectorsLayerRef.current = L.layerGroup().addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Tile Layer when mapStyle changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !tileLayerRef.current) return;

    const lyrs = mapStyle === 'GOOGLE_SATELLITE' ? 'y' : 'm';
    const newUrl = `https://{s}.google.com/vt/lyrs=${lyrs}&x={x}&y={y}&z={z}`;
    tileLayerRef.current.setUrl(newUrl);
  }, [mapStyle]);

  // Update markers, vectors, and overlays when state changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    const vectorsLayer = vectorsLayerRef.current;

    if (!map || !markersLayer || !vectorsLayer) return;

    markersLayer.clearLayers();
    vectorsLayer.clearLayers();

    const mitigatingIds = new Set(mitigatingTowers.map((m) => m.cell_id));
    const mitigatingMap = new Map(mitigatingTowers.map((m) => [m.cell_id, m]));

    // 1. Plot Venue Marker & Influence Footprint (if available)
    if (venueLocation && venueLocation.lat && venueLocation.lon) {
      // 3.0 km Influence Radius
      L.circle([venueLocation.lat, venueLocation.lon], {
        radius: 3000,
        color: '#F59E0B',
        weight: 1.5,
        dashArray: '4, 6',
        fillColor: '#F59E0B',
        fillOpacity: 0.08,
      }).addTo(markersLayer);

      const venueIcon = L.divIcon({
        className: 'custom-venue-icon',
        html: `
          <div style="position: relative; display: flex; flex-direction: column; align-items: center;">
            <div style="background: #F59E0B; border: 2px solid #FFF; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px rgba(245, 158, 11, 0.8);">
              <span style="font-size: 11px; font-weight: bold; color: #000;">★</span>
            </div>
            <div style="background: #0E1526; border: 1px solid #F59E0B; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-family: monospace; font-weight: bold; color: #F59E0B; margin-top: 3px; white-space: nowrap;">
              VENUE: ${venueLocation.name.substring(0, 20)}
            </div>
          </div>
        `,
        iconSize: [120, 40],
        iconAnchor: [60, 11],
      });

      L.marker([venueLocation.lat, venueLocation.lon], { icon: venueIcon })
        .bindPopup(`
          <div style="font-family: monospace; font-size: 11px;">
            <div style="color: #F59E0B; font-weight: bold; margin-bottom: 4px;">★ EVENT EPICENTER VENUE</div>
            <div style="color: #F1F5F9; font-weight: 600;">${venueLocation.name}</div>
            <div style="color: #94A3B8; font-size: 10px; margin-top: 2px;">Coords: ${venueLocation.lat.toFixed(4)}°N, ${venueLocation.lon.toFixed(4)}°E</div>
            <div style="color: #F59E0B; font-size: 10px; margin-top: 2px;">Influence Horizon: 3.0 km Radius</div>
          </div>
        `)
        .addTo(markersLayer);
    }

    // 2. Filter cells according to selected filter
    const visibleCells = cells.filter((c) => {
      if (filterMode === 'SURGE_ONLY') {
        return c.cell_id === surgeTower?.cell_id || mitigatingIds.has(c.cell_id);
      }
      if (filterMode === 'CBD') return c.region === 'Central Business District';
      if (filterMode === 'WHITEFIELD') return c.region === 'Whitefield';
      if (filterMode === 'ECITY') return c.region === 'Electronic City';
      return true;
    });

    // 3. Plot Cell Towers
    visibleCells.forEach((c) => {
      const lat = c.lat ?? c.latitude ?? 12.9716;
      const lon = c.lon ?? c.longitude ?? 77.5946;
      const isSurge = surgeTower && c.cell_id === surgeTower.cell_id;
      const isMitigating = mitigatingIds.has(c.cell_id);
      const isSelected = selectedCellId === c.cell_id;
      const mitData = mitigatingMap.get(c.cell_id);

      let markerHtml = '';

      if (isSurge) {
        // Surge Epicenter: pulsating red radar marker
        markerHtml = `
          <div style="position: relative; display: flex; flex-direction: column; align-items: center; cursor: pointer;">
            <div class="radar-ring"></div>
            <div style="background: #EF4444; border: 2px solid #FFF; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 18px #EF4444; z-index: 10;">
              <span style="font-size: 10px; font-weight: 900; color: #FFF;">!</span>
            </div>
            <div style="background: #7F1D1D; border: 1px solid #EF4444; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-family: monospace; font-weight: bold; color: #FCA5A5; margin-top: 4px; white-space: nowrap;">
              ${c.cell_id} [${surgeTower.overload_pct}% OVERLOAD]
            </div>
          </div>
        `;
      } else if (isMitigating && mitData) {
        // Mitigating Donor Tower: glowing cyan marker with offload relief badge
        markerHtml = `
          <div style="position: relative; display: flex; flex-direction: column; align-items: center; cursor: pointer;">
            <div style="background: #06B6D4; border: 2px solid #A5F3FC; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 14px rgba(6, 182, 212, 0.8); z-index: 10;">
              <span style="font-size: 9px; font-weight: 900; color: #083344;">⇄</span>
            </div>
            <div style="background: #083344; border: 1px solid #06B6D4; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-family: monospace; font-weight: bold; color: #67E8F9; margin-top: 3px; white-space: nowrap;">
              ${c.cell_id} (+${mitData.offload_allocated_mbps}M)
            </div>
          </div>
        `;
      } else {
        // Normal Cell Tower
        const color = c.initial_state === 'STANDBY' ? '#A855F7' : c.is_emergency ? '#F59E0B' : '#10B981';
        const borderColor = isSelected ? '#FFFFFF' : '#047857';
        const size = isSelected ? 16 : 11;
        markerHtml = `
          <div style="width: ${size}px; height: ${size}px; border-radius: 50%; background: ${color}; border: 1.5px solid ${borderColor}; box-shadow: 0 0 6px ${color}80; cursor: pointer;"></div>
        `;
      }

      const icon = L.divIcon({
        className: 'custom-tower-marker',
        html: markerHtml,
        iconSize: isSurge ? [140, 50] : isMitigating ? [130, 45] : [16, 16],
        iconAnchor: isSurge ? [70, 11] : isMitigating ? [65, 9] : [8, 8],
      });

      const marker = L.marker([lat, lon], { icon }).addTo(markersLayer);

      // Popup Content
      let popupContent = `
        <div style="font-family: monospace; font-size: 11px; line-height: 1.4;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1E293B; padding-bottom: 4px; margin-bottom: 6px;">
            <span style="font-weight: bold; color: ${isSurge ? '#EF4444' : isMitigating ? '#06B6D4' : '#10B981'};">
              ${isSurge ? '🚨 SURGE EPICENTER TOWER' : isMitigating ? '⚡ DONOR MITIGATING TOWER' : 'CELL TOWER'}
            </span>
            <span style="color: #94A3B8; font-size: 10px;">${c.cell_id}</span>
          </div>
          <div><span style="color: #94A3B8;">Region:</span> <span style="color: #F1F5F9;">${c.region}</span></div>
          <div><span style="color: #94A3B8;">State:</span> <span style="color: ${c.current_state === 'STANDBY' ? '#A855F7' : '#10B981'}; font-weight: bold;">${c.current_state || c.initial_state}</span></div>
          <div><span style="color: #94A3B8;">Capacity:</span> <span style="color: #F1F5F9;">${c.capacity_mbps.toFixed(0)} Mbps</span></div>
          <div><span style="color: #94A3B8;">Base Load:</span> <span style="color: #F1F5F9;">${(c.base_load_mbps ?? 0).toFixed(0)} Mbps</span></div>
      `;

      if (isSurge && surgeTower) {
        popupContent += `
          <div style="margin-top: 6px; padding-top: 6px; border-top: 1px dashed #EF4444; color: #FCA5A5;">
            <div><strong>Surge Uplift:</strong> +${surgeTower.surge_uplift_mbps} Mbps</div>
            <div><strong>Total Unmitigated:</strong> ${surgeTower.total_demand_mbps} Mbps</div>
            <div><strong>Utilization:</strong> <span style="color: #EF4444; font-weight: bold;">${surgeTower.overload_pct}% (OVERLOAD)</span></div>
            <div><strong>Required Offload:</strong> ${surgeTower.deficit_mbps} Mbps</div>
          </div>
        `;
      } else if (isMitigating && mitData) {
        popupContent += `
          <div style="margin-top: 6px; padding-top: 6px; border-top: 1px dashed #06B6D4; color: #67E8F9;">
            <div><strong>Distance from Epicenter:</strong> ${mitData.distance_km} km</div>
            <div><strong>Headroom Before:</strong> ${mitData.headroom_before_mbps} Mbps</div>
            <div><strong>Offload Absorbed:</strong> +${mitData.offload_allocated_mbps} Mbps</div>
            <div><strong>Post-Mitigation Util:</strong> <span style="color: #10B981; font-weight: bold;">${mitData.util_after_pct}% (Safe &lt; 78%)</span></div>
          </div>
        `;
      }

      popupContent += `
        <div style="margin-top: 6px; color: #64748B; font-size: 9px;">Click tower to inspect telemetry</div>
      </div>`;

      marker.bindPopup(popupContent);
      marker.on('click', () => {
        onSelectCell(c.cell_id);
      });
    });

    // 4. Draw Dynamic Load-Splitting Vectors from Surge Tower to Mitigating Donors
    if (surgeTower) {
      loadVectors.forEach((vec) => {
        const polyline = L.polyline([vec.from_coords, vec.to_coords], {
          color: '#06B6D4',
          weight: 2.5,
          opacity: 0.85,
          dashArray: '6, 8',
        }).addTo(vectorsLayer);

        polyline.bindTooltip(
          `<div style="font-family: monospace; font-size: 10px; font-weight: bold; color: #06B6D4; background: #083344; padding: 2px 6px; border-radius: 4px; border: 1px solid #06B6D4;">${vec.label}</div>`,
          { permanent: true, direction: 'center', className: 'vector-tooltip' }
        );
      });
    }

    // Auto-fit bounds if surge tower is active
    if (surgeTower) {
      const surgeCoords = [surgeTower.lat, surgeTower.lon] as [number, number];
      map.setView(surgeCoords, 13, { animate: true });
    }
  }, [cells, surgeTower, mitigatingTowers, loadVectors, venueLocation, filterMode, selectedCellId, onSelectCell]);

  const handleResetView = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView([12.9716, 77.5946], 12, { animate: true });
    }
  };

  const handleFocusSurge = () => {
    if (mapInstanceRef.current && surgeTower) {
      mapInstanceRef.current.setView([surgeTower.lat, surgeTower.lon], 14, { animate: true });
    }
  };

  return (
    <div className={`relative bg-noc-surface border border-noc-border rounded-lg overflow-hidden flex flex-col ${className}`}>
      {/* Top Map Action Strip */}
      <div className="p-3 bg-noc-surface border-b border-noc-border flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-noc-cyan animate-pulse" />
          <span className="text-xs font-mono font-bold text-slate-100">
            BENGALURU GEOGRAPHICAL CELL TOPOLOGY
          </span>
          <span className="text-[10px] font-mono text-slate-400 bg-noc-bg px-2 py-0.5 rounded border border-noc-border">
            100 CELL TOWERS PLOTTED
          </span>
          <Badge type="PUBLIC_SOURCE" label="GOOGLE MAPS CDN" />
        </div>

        {/* Filters and Controls */}
        <div className="flex items-center gap-1.5 text-xs font-mono">
          {/* Google Maps Style Toggle */}
          <div className="flex bg-noc-bg rounded p-0.5 border border-noc-border mr-1">
            <button
              onClick={() => setMapStyle('GOOGLE_DARK')}
              className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
                mapStyle === 'GOOGLE_DARK' ? 'bg-noc-cyan text-noc-bg' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              GMaps Dark
            </button>
            <button
              onClick={() => setMapStyle('GOOGLE_ROADMAP')}
              className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
                mapStyle === 'GOOGLE_ROADMAP' ? 'bg-noc-cyan text-noc-bg' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              GMaps Normal
            </button>
            <button
              onClick={() => setMapStyle('GOOGLE_SATELLITE')}
              className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
                mapStyle === 'GOOGLE_SATELLITE' ? 'bg-noc-cyan text-noc-bg' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Satellite
            </button>
          </div>

          <button
            onClick={() => setFilterMode('ALL')}
            className={`px-2.5 py-1 rounded text-[11px] transition-colors ${
              filterMode === 'ALL'
                ? 'bg-noc-cyan text-noc-bg font-bold'
                : 'bg-noc-bg text-slate-400 hover:text-slate-200 border border-noc-border'
            }`}
          >
            All 100 Towers
          </button>
          <button
            onClick={() => setFilterMode('SURGE_ONLY')}
            className={`px-2.5 py-1 rounded text-[11px] transition-colors ${
              filterMode === 'SURGE_ONLY'
                ? 'bg-noc-amber text-noc-bg font-bold'
                : 'bg-noc-bg text-slate-400 hover:text-slate-200 border border-noc-border'
            }`}
          >
            Surge & Donors Only
          </button>
          <button
            onClick={() => setFilterMode('CBD')}
            className={`px-2 py-1 rounded text-[11px] transition-colors ${
              filterMode === 'CBD'
                ? 'bg-slate-200 text-noc-bg font-bold'
                : 'bg-noc-bg text-slate-400 hover:text-slate-200 border border-noc-border'
            }`}
          >
            CBD / Palace Grounds
          </button>

          {surgeTower && (
            <button
              onClick={handleFocusSurge}
              className="px-2.5 py-1 rounded text-[11px] bg-red-950 border border-red-500 text-red-300 font-bold hover:bg-red-900 transition-colors flex items-center gap-1"
            >
              <Zap className="w-3 h-3 text-red-400" />
              Focus Epicenter
            </button>
          )}

          <button
            onClick={handleResetView}
            className="p-1 rounded bg-noc-bg text-slate-400 hover:text-slate-200 border border-noc-border"
            title="Reset to City Overview"
          >
            <Compass className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Leaflet Map Canvas with Google Maps direct raster tiles */}
      <div
        ref={mapContainerRef}
        className={`w-full flex-1 min-h-[460px] bg-[#0B0F19] ${
          mapStyle === 'GOOGLE_DARK'
            ? 'gmaps-dark-tiles'
            : mapStyle === 'GOOGLE_SATELLITE'
            ? 'gmaps-satellite-tiles'
            : ''
        }`}
      />

      {/* Bottom Map Legend Bar */}
      <div className="px-3 py-2 bg-noc-surface/95 border-t border-noc-border flex items-center justify-between text-[10px] font-mono text-slate-400 z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_8px_#EF4444]" />
            <span className="text-red-400 font-semibold">Surge Epicenter Tower</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#06B6D4]" />
            <span className="text-cyan-400 font-semibold">Mitigating Donor Tower</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 border-t-2 border-dashed border-cyan-400" />
            <span className="text-cyan-300">Load-Splitting Vector</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span>Active Sector Tower</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-purple-500" />
            <span>Standby Booster Tower</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-slate-400">
          <span>Lat: 12.9716°N, Lon: 77.5946°E (Bengaluru NOC Center)</span>
        </div>
      </div>
    </div>
  );
};
