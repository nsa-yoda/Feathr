# Failure Model

Failures are classified as **transient**, **permanent**, or **unknown**.

- transient: timeouts, temporary connection failures, retriable service responses;
- permanent: invalid data/invariants, duplicate identity with different payload, non-retriable client errors;
- unknown: conservative bounded retry followed by DLQ with bounded safe diagnostic context, never infinite retry.

Every background worker operation must end in exactly one disposition: success/ack, retry with scheduled visibility, or DLQ/redrive. There is no "log and forget" path.

The persistence worker's stable reason codes are `mongo_dependency` for translated dependency failures, `invalid_envelope` for malformed canonical messages, `event_conflict` for an immutable ID with a different payload hash, and `unknown_failure` for other bounded exceptions. DLQ diagnostics retain classification, reason code, message identity, and receive count; raw exception text and arbitrary metadata are excluded.

Dependency failures must be reflected in component health and metrics by the lifecycle/observability features that own those surfaces. Feature 007 exposes worker retry/DLQ counters and safe disposition logs; no endpoint silently substitutes semantically different data sources merely to return 200.
