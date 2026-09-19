# Data Model: ACR1 Storage Bootstrap Integrity

## Storage Manifest

An immutable application declaration, not a Mongo document.

| Field | Rule |
|---|---|
| `schema_version` | Positive integer; version 1 for this feature |
| `minimum_compatible_version` | Version 1 |
| `collections` | Fixed logical names for events, checkpoints, rebuild records, rebuild leases, and schema state |
| `indexes` | Deterministically ordered named index definitions per collection |
| `fingerprint` | SHA-256 of canonical manifest JSON; safe to log |

## Schema State

One document in the schema-state collection.

| Field | Rule |
|---|---|
| `_id` | Constant `event_platform_storage` |
| `schema_version` | Exact applied version |
| `manifest_fingerprint` | Must equal the running application's manifest fingerprint |
| `applied_at` | UTC timestamp set by the first successful bootstrap actor |

The document is created with insert-only semantics. Later bootstrap actors verify it and cannot silently rewrite a different version or fingerprint.

## Bootstrap Definition

| Collection | Required access paths |
|---|---|
| events | unique `event_id`; descending `(timestamp,event_id)`; filtered type/user/source URL prefixes followed by descending time and ID |
| search projection checkpoints | unique `projector` lookup/upsert |
| search rebuild records | unique `rebuild_id`; descending `started_at` latest-history lookup |
| search rebuild leases | built-in unique `_id_` for the fixed lease record |
| storage schema | built-in unique `_id_` for the fixed schema-state record |

## Compatibility Result

| Field | Rule |
|---|---|
| `schema_version` | Observed compatible version |
| `manifest_fingerprint` | Observed matching fingerprint |
| `verified_indexes` | Count of required index definitions checked |

## State Transitions

```text
absent storage
  -> bootstrap creates indexes
  -> bootstrap inserts schema state
  -> verification succeeds

compatible storage
  -> bootstrap is idempotent
  -> verification succeeds

missing/drifted index or marker/version/fingerprint mismatch
  -> verification fails safely
  -> application does not start workers or accept traffic
```
