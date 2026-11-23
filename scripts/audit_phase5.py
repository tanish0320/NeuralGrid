from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from apps.api.app.config import Settings
from apps.api.app.core.state import AppContainer

def audit_phase5():
    c = AppContainer(settings=Settings())
    events = c.event_repo.list_events()
    impacts = c.impact_repo.list_all_impacts()
    cells = c.network_repo.get_cells(c.network_repo.get_current_network().network_id)
    
    print(f"=== PART A AUDIT: CANONICAL EVENTS & IMPACT RECORDS ===")
    print(f"Total Canonical Events: {len(events)}")
    print(f"Total Persisted Impact Records: {len(impacts)}")
    
    # 1. Unresolved events analysis
    unresolved = [e for e in events if e.latitude is None or e.longitude is None]
    print(f"\n1. Geographically Unresolved Events: {len(unresolved)}")
    for e in unresolved:
        prov = e.field_provenance or {}
        reason = "Venue unknown / no match in Bengaluru registry" if not e.venue_name else f"Venue '{e.venue_name}' coordinates unresolved"
        print(f"   - [{e.event_id.hex[:8]}] '{e.name[:40]}' | Venue: '{e.venue_name}' | Reason: {reason}")
        
    # 2. Category distribution of events
    categories = Counter(e.event_type for e in events)
    print(f"\n2. Category Breakdown: {dict(categories)}")

    # 3. Check the CBD cells with 17 simultaneous events:
    # Let's inspect which cells have max events
    impact_by_cell = {}
    for imp in impacts:
        impact_by_cell.setdefault(imp.cell_id, []).append(imp)
        
    max_cells = sorted(impact_by_cell.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    print(f"\n3. Top Congested / Overlapping Cells:")
    for cell_id, cell_impacts in max_cells:
        cell_obj = next((cl for cl in cells if cl.cell_id == cell_id), None)
        region = cell_obj.region if cell_obj else "Unknown"
        print(f"   Cell {cell_id} ({region}): {len(cell_impacts)} impacts")
        # List the events causing this
        ev_ids = [imp.event_id for imp in cell_impacts]
        for idx, imp in enumerate(cell_impacts):
            ev = next((e for e in events if e.event_id == imp.event_id), None)
            if ev:
                print(f"      [{idx+1}] {ev.name[:35]} | Start: {ev.start_at} | End: {ev.end_at} | Category: {ev.event_type} | Coords: ({ev.latitude}, {ev.longitude}) | Dist: {imp.geographic_distance_km}km | Delta: {imp.estimated_demand_delta_mbps}M")
            else:
                print(f"      [{idx+1}] Event {imp.event_id} (missing in event_repo)")

    # 4. Check sublinear stability
    deltas = [imp.estimated_demand_delta_mbps for imp in cell_impacts]
    sorted_d = sorted(deltas, reverse=True)
    naive_sum = sum(sorted_d)
    sublinear = sorted_d[0] + sum(d / (1.0 + 0.35 * i) for i, d in enumerate(sorted_d[1:], 1))
    print(f"\n4. Sub-linear Aggregation Behavior on Max Cell ({cell_id}):")
    print(f"   Naive Linear Sum:     {naive_sum:.2f} Mbps")
    print(f"   Sublinear Aggregated: {sublinear:.2f} Mbps (Discount: -{naive_sum - sublinear:.2f} Mbps)")
    print(f"   Effective Concurrency Reduction: {((naive_sum - sublinear) / naive_sum * 100):.1f}%")

if __name__ == "__main__":
    audit_phase5()
