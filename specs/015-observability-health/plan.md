# Implementation Plan: Observability and Health

**Branch**: `015-observability-health` | **Status**: Accepted

## Technical approach

Add a small dependency-free metrics registry and typed health registry under the
observability boundary. Keep probes injectable so unit and failure tests do not
need live services. Extend the existing request middleware to validate inbound
UUID correlation and emit completion metrics/logs. Add health and Prometheus
routes, initialize registries in lifespan, and preserve the existing structured
logging formatter and problem contract.

## Boundaries

- Health probes return only allowlisted states and details.
- Metrics labels are fixed to method, route family, status family, component,
  backend, and outcome; route normalization removes identifiers.
- Dependency clients remain lifespan-owned and no probe performs I/O unless an
  application-provided probe explicitly does so.

## Constitution check

PASS: typed boundaries, async lifecycle ownership, safe logging, bounded
cardinality, explicit degraded semantics, and deterministic tests are preserved.
