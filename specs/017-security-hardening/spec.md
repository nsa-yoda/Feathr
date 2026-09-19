# Feature Specification: Security Hardening

**Feature Branch**: `017-security-hardening`
**Created**: 2026-09-18
**Status**: Accepted
**Input**: User description: "Feature Request: Security Hardening"

## User Scenarios & Testing

### User Story 1 - Bound hostile HTTP input (Priority: P1)

As an API operator, I need request bodies, query strings, metadata, and continuation tokens to be bounded before expensive parsing or downstream work so that abusive input cannot exhaust service memory or dependency capacity.

**Why this priority**: Input exhaustion is the primary externally reachable security risk for this unauthenticated demo API.

**Independent Test**: Send oversized bodies, query values, cursor values, and metadata structures through the HTTP boundary and verify bounded problem responses with no dependency call or raw input echo.

**Acceptance Scenarios**:

1. **Given** a request whose declared or streamed body exceeds the configured limit, **when** it reaches the service, **then** the service returns a safe 413 problem response before route parsing completes.
2. **Given** a search term, query filter, cursor, page size, or date range outside its documented bound, **when** the request is validated, **then** the service returns a safe 422 problem response without constructing arbitrary downstream DSL.
3. **Given** deeply nested, oversized, or unsupported event metadata, **when** ingestion validates it, **then** the request is rejected using the Feature 002 bounded validation categories without logging or echoing the metadata.

### User Story 2 - Restrict browser and network trust boundaries (Priority: P1)

As a reviewer, I need browser access and client identity handling to be explicit so that another origin or spoofed forwarding header cannot silently gain access or alter rate-limit identity.

**Why this priority**: The reviewer UI requires CORS, while forwarding headers and wildcard origins are common security footguns.

**Independent Test**: Exercise preflight and normal cross-origin requests for the configured origin and an unconfigured origin, and compare rate-limit identity with and without trusted proxy configuration.

**Acceptance Scenarios**:

1. **Given** an exact configured UI origin, **when** it sends a CORS request, **then** the response permits that origin and only the documented methods and headers.
2. **Given** a different origin or a wildcard configuration attempt, **when** it sends a CORS request, **then** the service does not grant that origin access.
3. **Given** the default trusted-proxy setting, **when** a caller supplies `X-Forwarded-For`, **then** rate limiting uses the direct peer identity; only an explicitly configured trusted hop chain may influence identity.

### User Story 3 - Operate without secret or diagnostic leakage (Priority: P2)

As an operator, I need errors, logs, dependency clients, and container images to fail safely so that secrets and debug internals are not exposed during normal operation.

**Why this priority**: Safe diagnostics and least-privilege runtime defaults protect the reviewer environment and make failures actionable without exposing credentials.

**Independent Test**: Trigger validation, dependency, and startup failures with sentinel credentials; inspect structured logs/responses and verify security headers, bounded client timeouts, and non-root image declarations.

**Acceptance Scenarios**:

1. **Given** a malformed request or unexpected dependency failure, **when** the service responds, **then** the problem document contains generic bounded detail and no stack trace, credentials, request body, or raw driver message.
2. **Given** configured dependency URLs or credentials, **when** startup logs configuration failures, **then** only safe field names and error categories are emitted.
3. **Given** an API response, **when** it is sent to a browser, **then** security-sensitive headers include content-type sniffing, framing, referrer, and restrictive content policy protections.
4. **Given** the application or UI container image is built, **when** its process runs, **then** it uses a non-root user and does not require debug mode.

## Edge Cases

- A request omits `Content-Length` and streams chunks larger than the body limit; the receive wrapper counts bytes and terminates the request.
- A chunked request sends a final chunk after the limit; the service does not continue buffering or invoke route validation.
- `cors_allowed_origin` is empty, wildcard, has credentials embedded, or contains a path; settings reject it or disable CORS safely.
- A malformed, oversized, non-ASCII, or signature-invalid cursor is rejected without attempting a dependency search.
- A query contains control characters, an invalid UTC range, or a page size over the route contract; it receives the same safe validation shape. A raw query string over 8 KiB is rejected at the HTTP boundary with safe 414 `request_query_too_large`.
- A client sends malformed forwarding headers, a chain with the wrong number of hops, or a non-IP value; the direct peer remains the identity.
- A configured dependency timeout is below or above supported bounds; settings reject it before client creation.
- A startup failure includes a secret-like URL; logs name only `startup` and the exception type.

## Requirements

### Functional Requirements

- **FR-001**: The HTTP boundary MUST enforce a configurable request body maximum before unbounded JSON parsing, using both declared length and streamed byte counting, and return a safe 413 problem response.
- **FR-002**: The event domain MUST continue enforcing Feature 002 metadata depth, key, string, list, numeric, type, and serialized-size bounds before persistence or queue admission.
- **FR-003**: Search and query inputs MUST enforce bounded lengths, printable/control-character rules, UTC date ranges, page sizes, and strict opaque cursor size/schema/signature validation.
- **FR-004**: Search requests MUST be translated into fixed application-generated Elasticsearch queries; clients MUST NOT provide raw DSL, scripts, field names, or arbitrary sort clauses.
- **FR-005**: CORS MUST be disabled unless an exact configured HTTP(S) UI origin is supplied; wildcard origins and credential-bearing origins MUST be rejected, and allowed methods/headers MUST be explicit.
- **FR-006**: Trusted proxy handling MUST remain disabled by default; forwarding headers may affect identity only when the configured hop count and complete IP chain match the direct peer.
- **FR-007**: Settings and startup diagnostics MUST use environment/configuration values without logging secret values, full URLs, credentials, request bodies, or raw dependency exception text.
- **FR-008**: Dependency probes and client operations introduced or hardened by this feature MUST use bounded timeouts from validated settings and classify timeout failures safely.
- **FR-009**: Normal API errors MUST use the project problem contract with generic bounded detail, no stack traces, and no debug mode; security headers MUST be emitted on API responses.
- **FR-010**: Application and UI container definitions MUST declare non-root runtime users and document local-only dependency security assumptions where applicable.
- **FR-011**: Tests MUST cover oversized declared/streamed bodies, oversized and unsafe queries/cursors, CORS allow/deny behavior, forwarding-header spoofing, metadata abuse, startup/error redaction, security headers, and non-root container declarations.
- **FR-012**: Documentation and traceability MUST describe all security limits, trust boundaries, CORS configuration, timeout defaults, local Elasticsearch security assumption, and verification commands.

### Key Entities

- **SecuritySettings**: Validated body, origin, proxy, timeout, and security-header configuration used at startup.
- **BoundedRequest**: An HTTP request whose declared and streamed body bytes are within the configured maximum.
- **TrustedProxyChain**: A validated forwarding-header chain with an exact configured hop count and direct-peer terminus.
- **SecurityHeaders**: Response protections for content sniffing, framing, referrers, and browser content execution.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of tested oversized declared and streamed bodies are rejected before route handler execution, with no request body or secret in the response/log capture.
- **SC-002**: 100% of tested invalid query, metadata, and cursor boundary cases return the documented safe problem shape without downstream dependency calls.
- **SC-003**: CORS tests permit exactly the configured origin and deny at least one different origin and every wildcard configuration attempt.
- **SC-004**: Forwarding-header tests show identical direct-peer identity under default settings and only the documented trusted chain behavior when explicitly enabled.
- **SC-005**: Every tested API error response includes the required problem fields and security headers, contains no stack trace or sentinel secret, and runs with debug disabled.
- **SC-006**: Static container checks prove both application and UI runtime users are non-root, and timeout/configuration checks prove bounded dependency operations.

## Assumptions

- The default body limit is 1 MiB and may be reduced or increased only within a 1 KiB to 16 MiB validated range.
- The default raw query-string limit is 8 KiB and may be configured only within 256 bytes to 64 KiB.
- CORS is disabled when `EVENT_PLATFORM_CORS_ALLOWED_ORIGIN` is unset; Compose/UI configuration supplies an exact origin later.
- A dependency operation timeout defaults to 5 seconds for client operations and remains bounded to 0.1–30 seconds; health probes may use a shorter internal deadline.
- Elasticsearch security is disabled only for the local single-node Compose demonstration; production deployments must add transport/authentication controls.
- Authentication and authorization are outside this feature and are not implied by these controls.
- Feature 021 owns the final multi-service Compose wiring; this feature supplies reusable non-root image definitions and security documentation.
