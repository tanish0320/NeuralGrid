from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from apps.api.app.core.database import utc_now
from apps.api.app.schemas.events import EventLifecycleStatus, EventRecord, VerificationStatus


class EventLifecycleManager:
    """Computes and updates canonical event lifecycle states and verification transitions."""

    @staticmethod
    def evaluate_lifecycle_status(
        current_status: str,
        start_at: datetime | None,
        end_at: datetime | None,
        now: datetime | None = None,
    ) -> EventLifecycleStatus:
        """Determine temporal lifecycle status: UPCOMING, ONGOING, COMPLETED, CANCELLED, POSTPONED."""
        if current_status in ("CANCELLED", "POSTPONED", "RECURRING"):
            return current_status  # type: ignore[return-value]

        if not start_at:
            return "UPCOMING"

        now = now or utc_now()
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        if end_at and end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)

        effective_end = end_at or (start_at.replace(hour=23, minute=59, second=59))

        if now < start_at:
            return "UPCOMING"
        elif start_at <= now <= effective_end:
            return "ONGOING"
        else:
            return "COMPLETED"

    @staticmethod
    def evaluate_verification_status(
        *,
        current_verification: str,
        lifecycle_status: str,
        source_records: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        manually_confirmed: bool = False,
    ) -> VerificationStatus:
        """Determine verification status:
        
        - CANCELLED: explicitly cancelled
        - EXPIRED: past end time and completed
        - CONFLICTED: substantive conflicts detected between sources
        - VERIFIED: official ticketing or manually confirmed
        - CORROBORATED: >= 2 independent sources (distinct domains, non-syndicated)
        - PARTIALLY_VERIFIED: 1 reputable source with extracted event fields
        - DISCOVERED: initial candidate
        """
        if lifecycle_status == "CANCELLED":
            return "CANCELLED"

        if manually_confirmed:
            return "VERIFIED"

        # Check for substantive conflicts
        has_critical_conflict = any(c.get("severity") in ("CRITICAL", "WARNING") for c in conflicts)
        if has_critical_conflict:
            return "CONFLICTED"

        # Check if source comes from authoritative ticketing / official portal
        authoritative_platforms = {"bookmyshow", "district", "allevents", "official_portal", "ticketing"}
        has_authoritative = any(
            any(auth in str(s.get("platform", "")).lower() or auth in str(s.get("source_id", "")).lower() for auth in authoritative_platforms)
            for s in source_records
        )
        if has_authoritative and len(source_records) >= 1:
            return "VERIFIED"

        # Check independent corroboration
        # Must have >= 2 distinct publisher domains AND distinct non-identical content
        distinct_domains = {
            s.get("domain", "").lower().replace("www.", "")
            for s in source_records
            if s.get("domain")
        }
        distinct_hashes = {
            s.get("content_hash")
            for s in source_records
            if s.get("content_hash")
        }

        # If multiple sources are just repeating the same syndicated press release/hash, do not count as independent
        is_syndicated_repetition = len(source_records) >= 2 and len(distinct_hashes) <= 1

        if len(distinct_domains) >= 2 and not is_syndicated_repetition:
            return "CORROBORATED"

        if len(source_records) >= 1:
            return "PARTIALLY_VERIFIED"

        return "DISCOVERED"
