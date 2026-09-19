# Feature 012 Data Model

## RebuildRecord

`rebuild_id`, `phase`, `started_at`, `completed_at`, `source_collection`, `old_index`, `target_index`, `scanned_count`, `indexed_count`, `failure_count`, bounded `failures`, `owner`, `lease_expires_at`, and `rollback_until`.

## RebuildStatus

Read-only response containing the same bounded identifiers, phase, counts, failure summary, and timestamps; it never contains event documents.
