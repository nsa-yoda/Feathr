# Feature Specification: Mandatory Rate Limiting

**Feature Branch**: `014-rate-limiting`
**Created**: 2026-09-18
**Status**: Accepted
**Input**: Feature request in `REQUEST.md`

## User Scenarios & Testing

### User Story 1 - Protect routes with distributed limits (Priority: P1)

As an API operator, I need every externally exposed application route classified into a bounded rate-limit policy so a burst from one client cannot exhaust the service or bypass limits by changing URLs.

**Why this priority**: Abuse protection is a mandatory platform capability and the distributed policy must work consistently across processes.

**Independent Test**: Exercise each route class against a configured Redis instance and verify allow, refill, deny, and independent-bucket behavior.

**Acceptance Scenarios**:

1. **Given** a client with available tokens, **When** it calls an ingestion, normal-read, expensive-read, or ops route, **Then** the request is allowed and standard limit headers describe the bucket.
2. **Given** a client has exhausted one route class, **When** it calls that same class again, **Then** the response is a 429 problem document with `Retry-After` and no internal key material.
3. **Given** the same client calls two route classes, **When** one class is exhausted, **Then** the other class retains its own allowance.

### User Story 2 - Preserve protection during Redis degradation (Priority: P1)

As an operator, I need a conservative bounded local limiter when Redis is unavailable so the service remains available without silently failing open.

**Why this priority**: Redis is derived coordination state; its outage must not turn into unrestricted request admission or total API outage.

**Independent Test**: Make the Redis adapter fail, issue requests from multiple identities, and verify local allow/deny behavior, degraded logging, and bounded eviction.

**Acceptance Scenarios**:

1. **Given** Redis is unavailable, **When** a request arrives, **Then** the local bucket is used, a structured degraded event is emitted, and the request is allowed or denied according to the conservative policy.
2. **Given** more unique identities than the configured local entry cap, **When** new requests arrive, **Then** idle entries are evicted and the limiter does not grow without bound.
3. **Given** a local bucket is denied, **When** its refill time arrives, **Then** a later request is allowed and its retry metadata is accurate.

### User Story 3 - Derive client identity safely (Priority: P1)

As an operator, I need rate-limit identity derived from the direct peer by default so an untrusted forwarding header cannot spoof a different bucket.

**Why this priority**: Identity errors defeat every route policy and can allow trivial abuse.

**Independent Test**: Send requests with and without forwarding headers under default and explicitly trusted-proxy settings and compare normalized identities.

**Acceptance Scenarios**:

1. **Given** trusted proxy hops are not configured, **When** a request includes `X-Forwarded-For`, **Then** the direct peer address remains the identity.
2. **Given** one trusted proxy hop is configured, **When** a valid forwarding chain arrives, **Then** the client address selected from the chain is used.
3. **Given** a malformed or too-short chain, **When** the request arrives, **Then** identity falls back to the direct peer safely.

## Edge Cases

- Missing peer address uses a fixed unknown identity rather than an unbounded or secret-bearing value.
- IPv4 and IPv6 textual forms normalize to one stable identity; whitespace and invalid forwarding entries are rejected.
- Zero refill or capacity configuration is rejected at startup; retry values are never negative.
- Redis returns malformed data or a script error: use local fallback and do not expose the Redis key or exception text.
- Health and metrics routes are exempt by default; their policy is explicit in configuration and tests.
- Concurrent requests for one Redis bucket are evaluated atomically; local updates are protected within the process.

## Requirements

### Functional Requirements

- **FR-001**: System MUST classify externally exposed routes as ingestion write, normal read/query, expensive read/search/analytics, or ops/status, with health/metrics explicitly exempt or separately configured.
- **FR-002**: System MUST enforce an atomic Redis-backed token bucket per normalized identity and route class, refilling by elapsed time and decrementing only when a request is allowed.
- **FR-003**: System MUST expose configurable bounded capacity, refill rate, and request cost for each route class, with safe startup validation.
- **FR-004**: System MUST return a 429 problem document for denials with `Retry-After`, `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` headers.
- **FR-005**: System MUST never include raw Redis keys, credentials, or dependency exception details in responses or logs.
- **FR-006**: System MUST use the direct peer IP by default and MUST ignore `X-Forwarded-For` unless a positive trusted-proxy-hop setting is configured.
- **FR-007**: System MUST parse trusted forwarding chains only up to the configured hop count and fall back to the direct peer for malformed chains.
- **FR-008**: System MUST use a conservative process-local token bucket when Redis cannot be used and MUST emit a structured degraded-state event.
- **FR-009**: System MUST cap local fallback memory and evict idle entries deterministically.
- **FR-010**: System MUST make token updates safe for concurrent requests within one process and preserve route-class isolation.
- **FR-011**: System MUST provide injectable clocks and deterministic token math for unit and failure tests.
- **FR-012**: System MUST document configuration, route classes, identity behavior, headers, degraded semantics, and operational verification.

### Key Entities

- **Route policy**: class, capacity, refill tokens per second, request cost, and whether the class is exempt.
- **Bucket state**: normalized identity, route class, token balance, last refill time, and idle expiry metadata.
- **Rate decision**: allow/deny, remaining tokens, reset timestamp, and whether Redis or local fallback made the decision.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Concurrent requests for one Redis bucket never observe more allowed requests than the configured capacity plus legitimately refilled tokens.
- **SC-002**: A denied request receives a 429 problem response and all four documented limit headers in every route class.
- **SC-003**: With Redis unavailable, requests remain protected by the local policy and local state remains at or below its configured entry cap.
- **SC-004**: Default forwarding-header tests demonstrate zero identity changes when trusted proxy hops are unset, and valid configured chains select the expected client.
- **SC-005**: Token arithmetic tests cover refill, deny, retry, expiry, route isolation, and boundary values with deterministic clocks.

## Assumptions

- The service is unauthenticated in this phase; IP identity is replaced by authenticated tenant/API-key identity in a later feature.
- Redis is optional derived coordination state, while local fallback is intentionally stricter and process-local.
- Health and metrics endpoints are exempt by default to preserve orchestration visibility.
- Configuration is supplied through the existing `EVENT_PLATFORM_` settings prefix and invalid values prevent startup.
