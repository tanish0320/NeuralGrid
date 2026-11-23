from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from apps.api.app.core.database import utc_now
from apps.api.app.modules.dependency_graph.graph_builder import haversine_km
from apps.api.app.modules.event_intelligence.geospatial.profiles import (
    EventCategoryProfile,
    compute_event_window,
    evaluate_temporal_surge_factor,
    generate_profile_sample_points,
    get_category_profile,
)
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.source_registry import SourceRegistryRepository
from apps.api.app.schemas.events import EventRecord
from apps.api.app.schemas.impact import (
    CellImpactAggregated,
    CellOverlapSummary,
    ContributingEventInfo,
    EventCellImpactRecord,
    EventImpactSummary,
    ImpactRecalculateResponse,
)
from apps.api.app.schemas.networks import CellRecord

logger = logging.getLogger(__name__)


class GeospatialImpactEngine:
    """
    Engine that maps canonical events onto the 100-cell Bengaluru network,
    evaluating distance attenuation, temporal surge profiles, and sub-linear multi-event saturation.
    """

    def __init__(
        self,
        event_repo: EventRepository,
        network_repo: NetworkRepository,
        impact_repo: ImpactRepository,
        registry_repo: SourceRegistryRepository | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.network_repo = network_repo
        self.impact_repo = impact_repo
        self.registry_repo = registry_repo

    def is_event_eligible(self, event: EventRecord, now: datetime | None = None) -> tuple[bool, str]:
        """
        Check if event is eligible for future demand impact mapping.
        Excludes cancelled and expired events.
        """
        if now is None:
            now = utc_now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Cancelled events produce 0 future impact
        if event.status == "CANCELLED" or event.verification_status == "CANCELLED":
            return False, "EVENT_CANCELLED"

        # Explicitly expired verification status
        if event.verification_status == "EXPIRED":
            return False, "EVENT_EXPIRED_STATUS"

        # Postponed without new date
        if event.status == "POSTPONED" and event.start_at is None:
            return False, "EVENT_POSTPONED_NO_DATE"

        # Check if past event window
        if event.end_at is not None:
            ev_end = event.end_at if event.end_at.tzinfo is not None else event.end_at.replace(tzinfo=timezone.utc)
            profile = get_category_profile(event.event_type)
            # Expired if end_at + departure hours is in the past
            from datetime import timedelta
            if ev_end + timedelta(hours=profile.departure_hours) < now:
                return False, "EVENT_TEMPORALLY_EXPIRED"

        return True, "ELIGIBLE"

    def map_event_to_cells(
        self,
        event: EventRecord,
        cells: list[CellRecord],
        now: datetime | None = None,
    ) -> list[EventCellImpactRecord]:
        """
        Maps a single canonical event to candidate cells within its category-specific radius.
        Returns empty list if event is ineligible or lacks coordinates.
        """
        eligible, reason = self.is_event_eligible(event, now)
        if not eligible:
            logger.info("Event %s excluded from cell mapping: %s", event.event_id, reason)
            return []

        # Missing coordinates handled gracefully without crashing or hallucinating
        if event.latitude is None or event.longitude is None:
            logger.warning("Event %s lacks venue coordinates; flagging as unresolved", event.event_id)
            return []

        profile = get_category_profile(event.event_type)
        radius_km = profile.radius_km

        # Effective attendance calculation
        attendance_is_estimated = False
        if event.attendance_low is not None and event.attendance_high is not None:
            effective_attendance = (event.attendance_low + event.attendance_high) / 2.0
            att_confidence = 0.90 if event.attendance_basis in ("SOURCE_EVIDENCE", "CONFIRMED", "TICKETING_DATA") else 0.75
        elif event.attendance_high is not None:
            effective_attendance = float(event.attendance_high)
            att_confidence = 0.85
        elif event.attendance_low is not None:
            effective_attendance = float(event.attendance_low)
            att_confidence = 0.80
        else:
            effective_attendance = float(profile.default_attendance)
            att_confidence = 0.50
            attendance_is_estimated = True

        # Base peak surge demand (Mbps)
        intensity = event.intensity if event.intensity > 0 else 1.0
        base_surge_mbps = (effective_attendance / 1000.0) * profile.mbps_per_1000_attendees * intensity

        # Source confidence
        v_status = event.verification_status
        if v_status in ("CORROBORATED", "VERIFIED", "MANUALLY_VERIFIED"):
            source_conf = 0.95
        elif v_status == "PARTIALLY_VERIFIED":
            source_conf = 0.75
        elif v_status == "DISCOVERED":
            source_conf = 0.60
        elif v_status == "CONFLICTED":
            source_conf = 0.40
        else:
            source_conf = 0.50

        # Venue confidence
        venue_conf = 0.95 if event.venue_name else 0.75

        # Composite impact confidence
        composite_confidence = round(source_conf * venue_conf * att_confidence, 4)

        # Time windows
        win_start, ev_start, ev_end, win_end = compute_event_window(profile, event.start_at, event.end_at)

        # Input evidence IDs
        evidence_ids: list[str] = []
        if self.registry_repo:
            evidences = self.registry_repo.list_evidence_for_event(event.event_id)
            evidence_ids = [e.evidence_id for e in evidences]
        if not evidence_ids and event.source_ids:
            evidence_ids = [str(s) for s in event.source_ids]

        timestamp = utc_now()
        impacts: list[EventCellImpactRecord] = []

        for cell in cells:
            if cell.initial_state == "STANDBY":
                continue

            dist_km = haversine_km(event.latitude, event.longitude, cell.lat, cell.lon)
            if dist_km > radius_km:
                continue

            # Distance attenuation: g(d) = (1 - d/R)^1.35
            norm_dist = dist_km / radius_km
            geo_relevance = round(max(0.0, (1.0 - norm_dist) ** 1.35), 4)
            if geo_relevance <= 0.0:
                continue

            # Cell demand delta
            demand_delta = round(base_surge_mbps * geo_relevance, 2)

            # Coverage relevance score (factoring cell capacity headroom and proximity)
            cap_factor = min(1.0, max(0.2, cell.capacity_mbps / 1200.0))
            cov_relevance = round(min(1.0, max(0.1, cap_factor * (1.0 - norm_dist * 0.4))), 4)

            # Impact category
            if norm_dist <= 0.40:
                impact_cat = "PRIMARY_HOTSPOT"
            elif norm_dist <= 0.75:
                impact_cat = "SECONDARY_ADJACENT"
            else:
                impact_cat = "PERIPHERAL_TRANSIT"

            # Temporal profile sample points
            sample_points = generate_profile_sample_points(
                profile=profile,
                window_start=win_start,
                event_start=ev_start,
                event_end=ev_end,
                window_end=win_end,
                peak_demand_mbps=demand_delta,
                sample_step_minutes=30,
            )

            temporal_dict = {
                "arrival_hours": profile.arrival_hours,
                "event_hours": round((ev_end - ev_start).total_seconds() / 3600.0, 2),
                "departure_hours": profile.departure_hours,
                "peak_multiplier": profile.event_peak_factor,
                "effective_attendance": int(effective_attendance),
                "attendance_estimated": attendance_is_estimated,
                "sample_points": sample_points,
            }

            impact_id = f"IMP-{event.event_id.hex[:8]}-{cell.cell_id}"

            impacts.append(
                EventCellImpactRecord(
                    impact_id=impact_id,
                    event_id=event.event_id,
                    cell_id=cell.cell_id,
                    geographic_distance_km=round(dist_km, 3),
                    geographic_relevance_score=geo_relevance,
                    coverage_relevance_score=cov_relevance,
                    estimated_demand_delta_mbps=demand_delta,
                    impact_confidence=composite_confidence,
                    impact_category=impact_cat,
                    impact_window_start=win_start,
                    impact_window_end=win_end,
                    temporal_profile=temporal_dict,
                    mapping_method="haversine_attenuation_v1.5",
                    scoring_model_version="v1.5",
                    input_evidence_ids=evidence_ids,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )

        impacts.sort(key=lambda item: (item.geographic_distance_km, item.cell_id))
        return impacts

    def aggregate_cell_impacts(
        self,
        cell: CellRecord,
        impacts: list[EventCellImpactRecord],
        events_by_id: dict[UUID, EventRecord],
    ) -> CellImpactAggregated:
        """
        Aggregates multiple event impacts affecting a single cell using sub-linear saturation.
        """
        if not impacts:
            proj_demand = cell.base_load_mbps
            util_pct = (proj_demand / cell.capacity_mbps) * 100.0 if cell.capacity_mbps > 0 else 0.0
            return CellImpactAggregated(
                cell_id=cell.cell_id,
                region=cell.region,
                capacity_mbps=cell.capacity_mbps,
                base_load_mbps=cell.base_load_mbps,
                current_load_mbps=cell.base_load_mbps,
                combined_demand_delta_mbps=0.0,
                projected_total_demand_mbps=round(proj_demand, 2),
                projected_utilisation_pct=round(util_pct, 2),
                congestion_risk_band="NORMAL",
                contributing_event_count=0,
                contributing_events=[],
                max_impact_window_start=None,
                max_impact_window_end=None,
            )

        # Sort contributions by estimated demand delta descending
        sorted_impacts = sorted(impacts, key=lambda x: x.estimated_demand_delta_mbps, reverse=True)

        # Sub-linear aggregation: delta_agg = delta_1 + sum_{i=2}^k delta_i / (1 + 0.35 * (i - 1))
        combined_delta = sorted_impacts[0].estimated_demand_delta_mbps
        for idx, imp in enumerate(sorted_impacts[1:], start=1):
            attenuation_div = 1.0 + 0.35 * idx
            combined_delta += imp.estimated_demand_delta_mbps / attenuation_div

        combined_delta = round(combined_delta, 2)
        projected_total = round(cell.base_load_mbps + combined_delta, 2)
        util_pct = round((projected_total / cell.capacity_mbps) * 100.0, 2) if cell.capacity_mbps > 0 else 0.0

        # Congestion risk band
        if util_pct < 70.0:
            risk_band = "NORMAL"
        elif util_pct < 85.0:
            risk_band = "ELEVATED"
        elif util_pct < 95.0:
            risk_band = "HIGH"
        else:
            risk_band = "CRITICAL"

        # Build contributing events info
        contributing_list: list[ContributingEventInfo] = []
        min_win_start = sorted_impacts[0].impact_window_start
        max_win_end = sorted_impacts[0].impact_window_end

        for imp in sorted_impacts:
            ev = events_by_id.get(imp.event_id)
            ev_title = ev.name if ev else f"Event {imp.event_id.hex[:6]}"
            ev_cat = ev.event_type if ev else "OTHER"
            v_name = ev.venue_name if ev else None

            contributing_list.append(
                ContributingEventInfo(
                    event_id=imp.event_id,
                    event_title=ev_title,
                    event_category=ev_cat,
                    venue_name=v_name,
                    distance_km=imp.geographic_distance_km,
                    demand_delta_mbps=imp.estimated_demand_delta_mbps,
                    impact_category=imp.impact_category,
                    impact_confidence=imp.impact_confidence,
                    impact_window_start=imp.impact_window_start,
                    impact_window_end=imp.impact_window_end,
                )
            )

            if imp.impact_window_start < min_win_start:
                min_win_start = imp.impact_window_start
            if imp.impact_window_end > max_win_end:
                max_win_end = imp.impact_window_end

        return CellImpactAggregated(
            cell_id=cell.cell_id,
            region=cell.region,
            capacity_mbps=cell.capacity_mbps,
            base_load_mbps=cell.base_load_mbps,
            current_load_mbps=cell.base_load_mbps,
            combined_demand_delta_mbps=combined_delta,
            projected_total_demand_mbps=projected_total,
            projected_utilisation_pct=util_pct,
            congestion_risk_band=risk_band,
            contributing_event_count=len(contributing_list),
            contributing_events=contributing_list,
            max_impact_window_start=min_win_start,
            max_impact_window_end=max_win_end,
        )

    def detect_overlapping_cells(
        self,
        cells: list[CellRecord],
        impacts: list[EventCellImpactRecord],
        events_by_id: dict[UUID, EventRecord],
    ) -> list[CellOverlapSummary]:
        """
        Detects cells affected by 2 or more simultaneous events, reporting linear sum vs sublinear aggregated demand.
        """
        impacts_by_cell: dict[str, list[EventCellImpactRecord]] = {}
        for imp in impacts:
            impacts_by_cell.setdefault(imp.cell_id, []).append(imp)

        cells_by_id = {c.cell_id: c for c in cells}
        overlaps: list[CellOverlapSummary] = []

        for cell_id, cell_impacts in impacts_by_cell.items():
            if len(cell_impacts) < 2:
                continue

            cell = cells_by_id.get(cell_id)
            region = cell.region if cell else "Unknown"

            # Check for temporal overlap among the events
            sorted_impacts = sorted(cell_impacts, key=lambda x: x.estimated_demand_delta_mbps, reverse=True)
            linear_sum = round(sum(i.estimated_demand_delta_mbps for i in sorted_impacts), 2)

            # Sub-linear aggregation
            agg_demand = sorted_impacts[0].estimated_demand_delta_mbps
            for idx, imp in enumerate(sorted_impacts[1:], start=1):
                agg_demand += imp.estimated_demand_delta_mbps / (1.0 + 0.35 * idx)
            agg_demand = round(agg_demand, 2)
            discount = round(linear_sum - agg_demand, 2)

            # Peak overlap window
            max_start = max(i.impact_window_start for i in sorted_impacts)
            min_end = min(i.impact_window_end for i in sorted_impacts)
            peak_start = max_start if max_start < min_end else sorted_impacts[0].impact_window_start
            peak_end = min_end if max_start < min_end else sorted_impacts[0].impact_window_end

            ev_ids = [i.event_id for i in sorted_impacts]
            ev_titles = [
                events_by_id.get(i.event_id).name if events_by_id.get(i.event_id) else str(i.event_id)[:8]
                for i in sorted_impacts
            ]

            cap = cell.capacity_mbps if cell else 1000.0
            base = cell.base_load_mbps if cell else 200.0
            total_load = base + agg_demand
            util = (total_load / cap) * 100.0

            if util < 70.0:
                risk = "NORMAL"
            elif util < 85.0:
                risk = "ELEVATED"
            elif util < 95.0:
                risk = "HIGH"
            else:
                risk = "CRITICAL"

            overlaps.append(
                CellOverlapSummary(
                    cell_id=cell_id,
                    region=region,
                    overlapping_event_count=len(sorted_impacts),
                    event_ids=ev_ids,
                    event_titles=ev_titles,
                    individual_demand_sum_mbps=linear_sum,
                    sublinear_aggregated_demand_mbps=agg_demand,
                    attenuation_discount_mbps=discount,
                    peak_overlap_window_start=peak_start,
                    peak_overlap_window_end=peak_end,
                    risk_band=risk,
                )
            )

        overlaps.sort(key=lambda x: (x.overlapping_event_count, x.sublinear_aggregated_demand_mbps), reverse=True)
        return overlaps

    def recalculate_all(
        self,
        network_id: UUID | None = None,
    ) -> ImpactRecalculateResponse:
        """
        Recalculates impact mappings across all canonical events for the specified (or current) network.
        """
        # Resolve network
        if network_id is not None:
            net = self.network_repo.get_network_by_id(network_id)
        else:
            net = self.network_repo.get_current_network()

        if not net:
            # Fallback or empty network
            return ImpactRecalculateResponse(
                status="NO_NETWORK_AVAILABLE",
                network_id=network_id,
                total_canonical_events=0,
                mapped_events_count=0,
                geographically_unresolved_count=0,
                excluded_events_count=0,
                total_impact_records=0,
                affected_cells_count=0,
                overlapping_cells_count=0,
                max_cell_demand_delta_mbps=0.0,
                avg_cell_demand_delta_mbps=0.0,
                category_distribution={},
                timestamp=utc_now(),
            )

        cells = self.network_repo.get_cells(net.network_id)
        events = self.event_repo.list_events()

        now = utc_now()
        mapped_events_count = 0
        unresolved_count = 0
        excluded_count = 0
        all_impacts: list[EventCellImpactRecord] = []
        category_dist: dict[str, int] = {}
        events_by_id: dict[UUID, EventRecord] = {}

        for event in events:
            events_by_id[event.event_id] = event
            category_dist[event.event_type] = category_dist.get(event.event_type, 0) + 1

            eligible, _ = self.is_event_eligible(event, now)
            if not eligible:
                excluded_count += 1
                self.impact_repo.delete_impacts_for_event(event.event_id)
                continue

            if event.latitude is None or event.longitude is None:
                unresolved_count += 1
                self.impact_repo.delete_impacts_for_event(event.event_id)
                continue

            event_impacts = self.map_event_to_cells(event, cells, now)
            if event_impacts:
                mapped_events_count += 1
                all_impacts.extend(event_impacts)
                self.impact_repo.delete_impacts_for_event(event.event_id)
                self.impact_repo.save_impacts(event_impacts)
            else:
                self.impact_repo.delete_impacts_for_event(event.event_id)

        # Overlapping cells
        overlaps = self.detect_overlapping_cells(cells, all_impacts, events_by_id)
        affected_cells = set(imp.cell_id for imp in all_impacts)
        max_delta = max((imp.estimated_demand_delta_mbps for imp in all_impacts), default=0.0)
        avg_delta = (
            round(sum(imp.estimated_demand_delta_mbps for imp in all_impacts) / len(all_impacts), 2)
            if all_impacts
            else 0.0
        )

        return ImpactRecalculateResponse(
            status="SUCCESS",
            network_id=net.network_id,
            total_canonical_events=len(events),
            mapped_events_count=mapped_events_count,
            geographically_unresolved_count=unresolved_count,
            excluded_events_count=excluded_count,
            total_impact_records=len(all_impacts),
            affected_cells_count=len(affected_cells),
            overlapping_cells_count=len(overlaps),
            max_cell_demand_delta_mbps=round(max_delta, 2),
            avg_cell_demand_delta_mbps=avg_delta,
            category_distribution=category_dist,
            timestamp=now,
        )
