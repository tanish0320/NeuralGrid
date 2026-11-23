from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from apps.api.app.core.database import parse_utc, utc_now
from apps.api.app.modules.event_intelligence.resolution.field_reconciler import (
    EventFieldReconciler,
    get_source_reliability,
)
from apps.api.app.modules.event_intelligence.resolution.lifecycle import EventLifecycleManager
from apps.api.app.modules.event_intelligence.resolution.similarity import (
    MatchScoreResult,
    compute_event_match_score,
)
from apps.api.app.modules.event_intelligence.resolution.venues import normalize_venue_name
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.source_registry import SourceRegistryRepository
from apps.api.app.schemas.events import (
    CanonicalEventDetailResponse,
    EventEvidenceRecord,
    EventHistoryRecord,
    EventRecord,
)

logger = logging.getLogger("neuralgrid.eventsense.resolver")


class CanonicalEventResolver:
    """Canonical event resolution, duplicate deduplication, evidence association,
    and history tracking engine."""

    def __init__(
        self,
        event_repo: EventRepository,
        registry_repo: SourceRegistryRepository | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.registry_repo = registry_repo

    def resolve_candidate(
        self,
        *,
        title: str,
        source_id: str,
        source_platform: str,
        source_url: str,
        domain: str,
        extracted_fields: dict[str, Any] | None = None,
        source_timestamp: datetime | None = None,
        content_hash: str | None = None,
        evidence_type: str = "NEWS_ANNOUNCEMENT",
        raw_metadata: dict[str, Any] | None = None,
        city_hint: str = "Bengaluru",
    ) -> tuple[EventRecord, bool, MatchScoreResult | None]:
        """Resolves an incoming extracted source item into either an existing canonical event or a new event."""
        fields = extracted_fields or {}
        raw_metadata = raw_metadata or {}
        now = utc_now()

        # Extract core fields
        name = (fields.get("name") or fields.get("event_name") or title or "").strip()
        venue_str = fields.get("venue_name") or fields.get("venue")
        venue_str = str(venue_str).strip() if venue_str else None

        canon_venue, canon_lat, canon_lon = normalize_venue_name(venue_str)
        effective_venue = canon_venue or venue_str
        effective_lat = canon_lat or fields.get("latitude")
        effective_lon = canon_lon or fields.get("longitude")

        start_at = fields.get("start_at")
        end_at = fields.get("end_at")
        if isinstance(start_at, str):
            try:
                start_at = parse_utc(start_at)
            except Exception:
                start_at = None
        if isinstance(end_at, str):
            try:
                end_at = parse_utc(end_at)
            except Exception:
                end_at = None

        # 1. Search existing events for matching canonical identity
        existing_events = self.event_repo.list_events()
        best_match: tuple[EventRecord, MatchScoreResult] | None = None

        for cand in existing_events:
            # Skip synthetic demo events from auto-merging unless key matches
            if cand.event_origin == "SEEDED_DEMO":
                continue

            match_res = compute_event_match_score(
                name_a=name,
                name_b=cand.name,
                venue_a=effective_venue,
                venue_b=cand.venue_name,
                start_a=start_at,
                start_b=cand.start_at,
                lat_a=float(effective_lat) if effective_lat is not None else None,
                lon_a=float(effective_lon) if effective_lon is not None else None,
                lat_b=cand.latitude,
                lon_b=cand.longitude,
                content_hash_a=content_hash,
                canonical_url_a=source_url,
            )

            if match_res.is_match:
                if best_match is None or match_res.confidence > best_match[1].confidence:
                    best_match = (cand, match_res)

        # 2. Case A: Matched an existing canonical event (Duplicate Resolution & Evidence Linkage)
        if best_match is not None:
            matched_event, match_info = best_match
            logger.info(
                f"Resolved candidate '{name}' to existing canonical event '{matched_event.name}' "
                f"(ID: {matched_event.event_id}, confidence: {match_info.confidence})"
            )

            # Reconcile fields and collect conflicts
            reconciled_fields, new_conflicts, updated_provenance = EventFieldReconciler.reconcile_fields(
                existing_event=matched_event,
                incoming_fields=fields,
                incoming_source_id=source_id,
                incoming_source_platform=source_platform,
                incoming_confidence=match_info.confidence,
            )

            # Record resolution metadata in provenance
            res_history = list(updated_provenance.get("resolution_history") or [])
            res_history.append(
                {
                    "source_id": source_id,
                    "matched_at": now.isoformat(),
                    "confidence": match_info.confidence,
                    "duplicate_type": match_info.duplicate_type,
                    "reasons": match_info.reasons,
                }
            )
            updated_provenance["resolution_history"] = res_history

            # Track source list in provenance
            sources_list = list(updated_provenance.get("sources") or [])
            if not any(s.get("source_id") == source_id or s.get("url") == source_url for s in sources_list):
                sources_list.append(
                    {
                        "source_id": source_id,
                        "platform": source_platform,
                        "domain": domain,
                        "content_hash": content_hash,
                        "url": source_url,
                    }
                )
            updated_provenance["sources"] = sources_list

            # Update source_ids
            existing_sources = list(matched_event.source_ids)
            source_uuid = UUID(source_id) if len(source_id) == 36 and "-" in source_id else uuid4()
            if source_uuid not in existing_sources:
                existing_sources.append(source_uuid)

            # Persist evidence record
            evidence_rec = EventEvidenceRecord(
                evidence_id=f"evid_{uuid4().hex[:12]}",
                event_id=matched_event.event_id,
                source_platform=source_platform,
                source_url=source_url,
                source_timestamp=source_timestamp,
                evidence_type=evidence_type,
                extracted_text=f"{name} | {effective_venue or 'Venue TBD'} | {source_url}",
                source_reliability=get_source_reliability(source_platform),
                evidence_confidence=match_info.confidence,
                raw_metadata=raw_metadata,
                created_at=now,
            )
            if self.registry_repo:
                self.registry_repo.add_evidence(evidence_rec)

            # Determine updated lifecycle & verification statuses
            lifecycle = EventLifecycleManager.evaluate_lifecycle_status(
                current_status=reconciled_fields["status"],
                start_at=reconciled_fields["start_at"],
                end_at=reconciled_fields["end_at"],
                now=now,
            )

            # Evaluate verification using full accumulated source history
            verification = EventLifecycleManager.evaluate_verification_status(
                current_verification=matched_event.verification_status,
                lifecycle_status=lifecycle,
                source_records=sources_list,
                conflicts=updated_provenance.get("conflicts", []),
                manually_confirmed=(matched_event.confirmed_at is not None),
            )

            # Update event record
            updated_event = matched_event.model_copy(
                update={
                    "name": reconciled_fields["name"],
                    "event_type": reconciled_fields["event_type"],
                    "venue_name": reconciled_fields["venue_name"],
                    "latitude": reconciled_fields["latitude"],
                    "longitude": reconciled_fields["longitude"],
                    "start_at": reconciled_fields["start_at"],
                    "end_at": reconciled_fields["end_at"],
                    "attendance_low": reconciled_fields["attendance_low"],
                    "attendance_high": reconciled_fields["attendance_high"],
                    "attendance_basis": reconciled_fields["attendance_basis"],
                    "status": lifecycle,
                    "verification_status": verification,
                    "source_ids": existing_sources,
                    "field_provenance": updated_provenance,
                    "updated_at": now,
                }
            )
            saved_event = self.event_repo.update_event(updated_event)

            # Log history entry
            history_entry = EventHistoryRecord(
                history_id=f"hist_{uuid4().hex[:12]}",
                event_id=matched_event.event_id,
                change_type="CORROBORATED" if verification == "CORROBORATED" else "FIELD_UPDATED",
                previous_state={"status": matched_event.status, "verification": matched_event.verification_status},
                new_state={"status": saved_event.status, "verification": saved_event.verification_status},
                reason=f"Matched from {source_platform} ({source_url}) with confidence {match_info.confidence}",
                recorded_at=now,
            )
            self.event_repo.add_history_entry(history_entry)

            return saved_event, False, match_info

        # 3. Case B: Create new canonical event
        new_event_id = uuid4()
        source_uuid = UUID(source_id) if len(source_id) == 36 and "-" in source_id else uuid4()

        initial_provenance: dict[str, Any] = {
            "sources": [
                {
                    "source_id": source_id,
                    "platform": source_platform,
                    "domain": domain,
                    "content_hash": content_hash,
                    "url": source_url,
                }
            ],
            "field_attribution": {
                "name": {
                    "source": source_id,
                    "platform": source_platform,
                    "score": get_source_reliability(source_platform),
                    "basis": "CONFIRMED" if get_source_reliability(source_platform) >= 0.85 else "INFERRED",
                },
                "venue_name": {
                    "source": source_id,
                    "basis": "CONFIRMED" if canon_venue else "INFERRED",
                },
            },
            "conflicts": [],
            "resolution_history": [
                {
                    "source_id": source_id,
                    "matched_at": now.isoformat(),
                    "confidence": 1.0,
                    "duplicate_type": "INITIAL_CREATION",
                    "reasons": ["First discovered instance of event"],
                }
            ],
        }

        # Initial lifecycle & verification
        lifecycle = EventLifecycleManager.evaluate_lifecycle_status(
            current_status="UPCOMING",
            start_at=start_at,
            end_at=end_at,
            now=now,
        )
        verification = EventLifecycleManager.evaluate_verification_status(
            current_verification="DISCOVERED",
            lifecycle_status=lifecycle,
            source_records=initial_provenance["sources"],
            conflicts=[],
        )

        new_event = EventRecord(
            event_id=new_event_id,
            event_key=None,
            event_origin="SOURCE_DISCOVERED",
            name=name,
            event_type=str(fields.get("event_type") or "public_event"),
            venue_name=effective_venue,
            city=str(fields.get("city") or city_hint),
            address=str(fields.get("address")) if fields.get("address") else None,
            latitude=float(effective_lat) if effective_lat is not None else None,
            longitude=float(effective_lon) if effective_lon is not None else None,
            start_at=start_at,
            end_at=end_at,
            attendance_low=int(fields["attendance_low"]) if fields.get("attendance_low") else None,
            attendance_high=int(fields["attendance_high"]) if fields.get("attendance_high") else None,
            attendance_basis="SOURCE_EVIDENCE" if fields.get("attendance_high") else "UNKNOWN",
            intensity=1.0,
            verification_status=verification,
            status=lifecycle,
            source_ids=[source_uuid],
            field_provenance=initial_provenance,
            created_at=now,
            updated_at=now,
        )
        saved_event = self.event_repo.create_event(new_event)

        # Persist initial evidence
        evidence_rec = EventEvidenceRecord(
            evidence_id=f"evid_{uuid4().hex[:12]}",
            event_id=new_event_id,
            source_platform=source_platform,
            source_url=source_url,
            source_timestamp=source_timestamp,
            evidence_type=evidence_type,
            extracted_text=f"{name} | {effective_venue or 'Venue TBD'} | {source_url}",
            source_reliability=get_source_reliability(source_platform),
            evidence_confidence=0.85,
            raw_metadata=raw_metadata,
            created_at=now,
        )
        if self.registry_repo:
            self.registry_repo.add_evidence(evidence_rec)

        # Log creation history
        history_entry = EventHistoryRecord(
            history_id=f"hist_{uuid4().hex[:12]}",
            event_id=new_event_id,
            change_type="CREATED",
            previous_state={},
            new_state={"status": saved_event.status, "verification": saved_event.verification_status},
            reason=f"Discovered by {source_platform} ({source_url})",
            recorded_at=now,
        )
        self.event_repo.add_history_entry(history_entry)

        return saved_event, True, None

    def get_canonical_event_detail(self, event_id: UUID | str) -> CanonicalEventDetailResponse | None:
        """Assembles rich canonical event details including associated evidence, field attribution,
        conflicts, and full audit history."""
        event = self.event_repo.get_event(event_id)
        if not event:
            return None

        evidence_list = (
            self.registry_repo.list_evidence_for_event(event.event_id)
            if self.registry_repo
            else []
        )
        history_list = self.event_repo.list_history_for_event(event.event_id)

        prov = event.field_provenance or {}
        field_attribution = prov.get("field_attribution", {})
        conflicts = prov.get("conflicts", [])
        resolution_metadata = {
            "source_count": len(event.source_ids),
            "evidence_count": len(evidence_list),
            "resolution_history": prov.get("resolution_history", []),
        }

        return CanonicalEventDetailResponse(
            event=event,
            evidence=evidence_list,
            field_attribution=field_attribution,
            conflicts=conflicts,
            resolution_metadata=resolution_metadata,
            history=history_list,
        )
