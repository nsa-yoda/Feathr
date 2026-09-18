# Feature 002 Research

## Decisions

### Typed boundary validation

Pydantic v2 models are already the repository boundary convention from Feature 001. Use typed datetime and HTTP URL parsing, explicit validators for timezone/future skew, and field validation plus a raw-input shape check for recursive metadata limits. Keep the domain module independent of FastAPI and infrastructure.

### Metadata policy

Metadata accepts JSON objects containing objects, arrays, strings, finite numbers, booleans, and null. Tuples and other non-JSON containers are rejected before Pydantic coercion. The contract uses a 16 KiB compact UTF-8 serialized limit, depth five, 64 total object keys, key length 1–64, string length 512, list length 128, and finite numbers with absolute value at most 10^18. These limits bound memory and downstream Elasticsearch mapping pressure while preserving flexible event payloads.

### Canonical hashing

Hash only the producer-controlled semantic fields. Serialize recursively sorted keys with compact separators, UTF-8, and `ensure_ascii=false`; reject non-finite numbers rather than producing platform-dependent tokens. SHA-256 produces a stable lowercase hexadecimal digest suitable for idempotency comparisons.

### Time and identity

The event input validator compares producer time to an injectable UTC clock and accepts five minutes of future skew. Canonical event creation accepts injected event IDs and ingestion clocks for deterministic tests; production callers use UUID4 and the current UTC time. Historical timestamps have no lower bound.

## Rejected alternatives

- No event-type enum: producers may add event types without a domain code deployment.
- No metadata flattening in the domain: Elasticsearch-specific projections belong to later features.
- No network URL verification: validation must remain deterministic and cannot make external calls.
- No hash of the full canonical event: server arrival time and identity must not change semantic payload identity.
