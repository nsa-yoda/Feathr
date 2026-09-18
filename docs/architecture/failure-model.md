# Failure Model

Failures are classified as **transient**, **permanent**, or **unknown**.

- transient: timeouts, temporary connection failures, retriable service responses;
- permanent: invalid data/invariants, duplicate identity with different payload, non-retriable client errors;
- unknown: conservative bounded retry followed by DLQ with full diagnostic context, never infinite retry.

Every background worker operation must end in exactly one disposition: success/ack, retry with scheduled visibility, or DLQ/redrive. There is no "log and forget" path.

Dependency failures must be reflected in component health and metrics. No endpoint silently substitutes semantically different data sources merely to return 200.
