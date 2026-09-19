# Feature Specification: Docker Compose Runtime

**Feature**: 021-docker-compose-runtime  
**Status**: Accepted for implementation  
**Source**: [REQUEST.md](REQUEST.md)

## User Scenarios & Testing

### User Story 1 - Start the complete reviewer stack (Priority: P1)

A reviewer copies the documented local environment file and runs one Compose command. The API, MongoDB replica set, Elasticsearch, Redis, and demo UI start in a predictable local network with health-based dependency ordering.

**Acceptance Scenarios**

1. Given Docker Compose is available and no project containers are running, when the reviewer runs `docker compose up --build -d`, then all required services reach their declared health or successful initialization state without arbitrary sleep-based ordering.
2. Given the stack has started, when the reviewer requests the API liveness and readiness endpoints, then liveness is successful and readiness reports Mongo canonical storage and lifecycle workers healthy; Elasticsearch and Redis are reported as healthy or degraded according to their configured role.
3. Given the reviewer runs `docker compose down -v`, when the stack is started again, then named data volumes are recreated and the initialization path remains idempotent.

### User Story 2 - Verify an end-to-end event flow (Priority: P1)

A reviewer runs the smoke command and receives a nonzero exit code if the stack cannot accept, persist, query, search, or aggregate an event within bounded deadlines.

**Acceptance Scenarios**

1. Given a healthy stack, when the smoke command posts a valid event, then the API returns `202` and the command records the event identifier without logging payload secrets.
2. Given the accepted event, when the command polls canonical query, Elasticsearch search, and realtime statistics, then each endpoint returns evidence for that event before its deadline.
3. Given an unhealthy or incomplete stack, when the smoke command reaches its deadline, then it exits nonzero and prints a bounded service/status diagnostic.

### User Story 3 - Operate the local runtime safely (Priority: P2)

A reviewer can understand configuration, reset data, inspect health, and run the API/UI without granting containers unnecessary privileges.

**Acceptance Scenarios**

1. Given `.env.example`, when the reviewer copies it to `.env`, then every documented default is non-secret and suitable for a local machine.
2. Given the container definitions, when the reviewer inspects the runtime, then the API and UI final images run as non-root users, the API has one Uvicorn worker, and resource settings are bounded for a common laptop.
3. Given the UI is running, when the reviewer opens its URL, then it serves the static reviewer shell and proxies `/api/` requests to the API service.

## Functional Requirements

- **FR-001**: The Compose project MUST define app, mongo, mongo-init, elasticsearch, redis, and ui services with pinned image tags or build contexts.
- **FR-002**: Service startup dependencies MUST use health checks and successful initialization completion; fixed sleeps MUST NOT be used as readiness coordination.
- **FR-003**: Mongo MUST run as a single-node replica set and mongo-init MUST idempotently initialize and verify that replica set within a bounded deadline.
- **FR-004**: The app MUST receive canonical Mongo, Elasticsearch, and Redis URLs through environment configuration, run one Uvicorn worker, and use bounded dependency timeouts.
- **FR-005**: The API and UI final containers MUST run without root privileges; the UI MUST expose a stable local port and proxy `/api/` to the API.
- **FR-006**: The stack MUST use named volumes for durable local service data and a dedicated network; `docker compose down -v` MUST be documented as the complete reset operation.
- **FR-007**: `.env.example` MUST document non-secret local defaults, exposed ports, image versions, and the optional Redis password behavior.
- **FR-008**: The smoke command MUST start or refresh the stack, wait for liveness/readiness with a monotonic deadline, ingest one event, poll canonical query and search, check realtime statistics, and return nonzero on any timeout or unexpected response.
- **FR-009**: Smoke diagnostics and container defaults MUST avoid credentials, request bodies, and full event metadata; service failures MUST be represented with bounded status text.
- **FR-010**: Compose configuration and smoke behavior MUST have automated regression coverage that does not require a live Docker daemon, while live Compose evidence is recorded when Docker is available.

## Edge Cases

- A stale Mongo data volume contains an already initialized replica set; initialization must succeed without reconfiguring it destructively.
- A dependency is reachable by TCP but not ready for its application protocol; health checks and the smoke deadline must detect this.
- A reviewer runs smoke twice; generated event identifiers and idempotency keys must avoid false positives from prior runs.
- A local Redis password is empty; the URL and health check must still be valid without printing the password.
- Docker is unavailable; configuration tests remain runnable and the smoke command reports the unavailable runtime rather than hanging.

## Success Criteria

- **SC-001**: A fresh local checkout can render `docker compose config` with no warnings caused by missing required variables after copying `.env.example`.
- **SC-002**: On a machine meeting the documented prerequisites, the clean stack reaches API readiness within 120 seconds in at least 19 of 20 repeated starts.
- **SC-003**: The smoke command completes its six HTTP checks (liveness, readiness, ingestion, canonical query, search, and realtime statistics) within 90 seconds and exits nonzero for a deliberately unavailable API.
- **SC-004**: Compose inspection shows no API/UI container configured with a root user or more than one Uvicorn worker.
- **SC-005**: The automated Compose contract tests pass without Docker and assert service names, health checks, dependency conditions, named volumes, bounded smoke behavior, and non-secret defaults.

## Assumptions and Scope

- Feature 023 owns the full React operations UI; this feature supplies its static shell, non-root image, and Compose wiring.
- Feature 022 owns the Postman reviewer collection; this feature only makes the API reachable for that workflow.
- Elasticsearch remains rebuildable and Redis remains non-authoritative; Mongo is the durable source of truth.
- Local defaults are for development and must be replaced for shared or production environments.
