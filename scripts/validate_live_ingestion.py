import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient(timeout=40.0) as client:
        # Check source registry
        reg_resp = await client.get("http://127.0.0.1:8000/api/v1/event-intelligence/sources/registry")
        sources = reg_resp.json()
        print(f"Total Registered Sources: {len(sources)}")

        enabled_sources = [s for s in sources if s.get("enabled", True)]
        print(f"Enabled Sources: {len(enabled_sources)}")

        # Trigger multi-source discovery across configured providers
        disc_req = {
            "city": "Bengaluru",
            "query_terms": ["concert", "festival", "Palace Grounds", "Chinnaswamy"],
            "time_window_hours": 168,
            "max_candidates": 5,
            "enabled_providers": [s["source_id"] for s in enabled_sources],
        }
        print("\n--- TRIGGERING LIVE DISCOVERY ---")
        disc_resp = await client.post("http://127.0.0.1:8000/api/v1/event-intelligence/discover", json=disc_req)
        disc_data = disc_resp.json()
        print("Discovery Run ID:", disc_data.get("run_id"))
        print("Discovery Status:", disc_data.get("status"))

        providers = disc_data.get("providers", [])
        print(f"\n--- RECORDS COLLECTED PER SOURCE ({len(providers)} providers responded) ---")
        total_records = 0
        failed_or_unavailable = 0
        for prov in providers:
            pname = prov.get("provider")
            cnt = prov.get("candidate_count", 0)
            status = prov.get("status")
            total_records += cnt
            if status in ("FAILED", "SKIPPED") or "AWAITING" in str(prov.get("error_code") or ""):
                failed_or_unavailable += 1
            print(f"  * {pname}: {cnt} items (Status: {status})")

        source_ids = disc_data.get("source_ids", [])
        print(f"\nTotal Discovered Items across all sources: {total_records}")
        print(f"Unique Deduplicated Sources Persisted: {len(source_ids)}")
        print(f"Duplicates / URLs Deduplicated during intake: {max(0, total_records - len(source_ids))}")

        # Execute crawl & extraction for first batch of valid sources
        if source_ids:
            crawl_req = {
                "run_id": disc_data["run_id"],
                "source_ids": source_ids[:5],
                "max_pages": 5,
            }
            print("\n--- RUNNING CRAWL & CANONICAL RESOLUTION ---")
            crawl_resp = await client.post("http://127.0.0.1:8000/api/v1/event-intelligence/crawl", json=crawl_req)
            crawl_data = crawl_resp.json()
            print("Pages Processed:", crawl_data.get("processed_count"))
            print("Linked Canonical Events:", len(crawl_data.get("event_ids", [])))

        # Inspect canonical events in database
        ev_resp = await client.get("http://127.0.0.1:8000/api/v1/events")
        all_events = ev_resp.json()

        verified_events = [e for e in all_events if e.get("verification_status") in ("VERIFIED", "MANUALLY_VERIFIED")]
        corroborated_events = [e for e in all_events if e.get("verification_status") == "CORROBORATED"]
        partially_verified = [e for e in all_events if e.get("verification_status") in ("PARTIALLY_VERIFIED", "SINGLE_SOURCE")]
        conflicted_events = [e for e in all_events if e.get("verification_status") == "CONFLICTED"]

        # Count total conflicts across all events
        total_conflicts = 0
        for ev in all_events:
            prov = ev.get("field_provenance") or {}
            conflicts = prov.get("conflicts") or []
            total_conflicts += len(conflicts)

        print("\n--- PHASE 4 SUMMARY METRICS ---")
        print(f"1. Total Records Collected Across Sources: {total_records}")
        print(f"2. Total Canonical Events in System: {len(all_events)}")
        print(f"3. Duplicates Resolved: {max(0, total_records - len(source_ids))}")
        print(f"4. Conflicting Records / Fields Detected: {total_conflicts}")
        print(f"5. Partially Verified Events: {len(partially_verified)}")
        print(f"6. Corroborated Events: {len(corroborated_events)}")
        print(f"7. Verified Events: {len(verified_events)}")
        print(f"8. Conflicted Events: {len(conflicted_events)}")
        print(f"9. Unavailable / Awaiting-Credentials Sources: {failed_or_unavailable}")

if __name__ == "__main__":
    asyncio.run(main())
