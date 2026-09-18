# Feature 002 Data Model

## EventInput

| Field | Type | Constraints |
|---|---|---|
| `event_type` | string | 1–128 characters, non-empty, no control characters |
| `timestamp` | datetime | ISO 8601, timezone-aware, normalized UTC, no more than five minutes future skew |
| `user_id` | string | 1–256 characters, non-empty, no control characters |
| `source_url` | HTTP URL | HTTP/HTTPS only, at most 2,048 characters |
| `metadata` | JSON object | 16 KiB compact UTF-8 max; depth 5; 64 total keys; key length 1–64; string length 512; finite numbers with absolute value ≤10^18; list length 128; no tuple/non-JSON coercion |

## CanonicalEvent

| Field | Type | Ownership |
|---|---|---|
| `event_id` | UUID | server-generated immutable identity |
| `event_type`, `timestamp`, `user_id`, `source_url`, `metadata` | normalized EventInput fields | producer semantics |
| `ingested_at` | UTC datetime | server-generated acceptance time |
| `schema_version` | literal `1` | server-owned contract version |
| `payload_hash` | lowercase SHA-256 hex | deterministic hash of producer fields |
| `idempotency_key_hash` | nullable lowercase SHA-256 hex | optional server-owned hash |

## Canonical payload

The hash input is an object with exactly the five producer fields. Object keys are recursively sorted; JSON is compact, UTF-8, and does not escape Unicode unnecessarily. Server identity, arrival time, schema version, and request IDs are excluded.
