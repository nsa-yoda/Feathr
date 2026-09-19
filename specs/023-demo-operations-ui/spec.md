# Feature Specification: Demo / Operations UI

**Feature**: 023-demo-operations-ui  
**Status**: Accepted for implementation  
**Source**: [REQUEST.md](REQUEST.md)

## User Scenarios & Testing

### User Story 1 - Inspect platform state (Priority: P1)

A reviewer opens the console and sees component health, queue/worker state, canonical event counts, projection status, and realtime/cache summaries with clear loading, empty, and degraded states.

**Acceptance Scenarios**

1. Given the API is reachable, when the dashboard loads, then health, queue, worker, projection, and realtime cards show values or an explicit unavailable state.
2. Given a dependency is degraded, when the dashboard refreshes, then the UI preserves the last successful values and displays a visible degraded message without exposing credentials or raw payloads.

### User Story 2 - Generate and inspect events (Priority: P1)

A reviewer submits one event or a bounded burst, sees accepted IDs or a problem response, and browses canonical events with filters and cursor navigation.

**Acceptance Scenarios**

1. Given valid form data, when the reviewer submits, then the UI displays the 202 status, event ID, and request ID.
2. Given invalid JSON, validation, rate-limit, or backpressure response, when submission fails, then the UI displays status, detail, and request ID in an accessible error region.
3. Given events exist, when filters and cursor controls are used, then the list updates with formatted metadata and never renders raw secrets.

### User Story 3 - Search, analyze, and operate (Priority: P2)

A reviewer searches eventually consistent projections, views hour/day/week analytics and realtime statistics, and reads operational health, retry, DLQ, checkpoint, and rebuild status.

**Acceptance Scenarios**

1. Search displays an eventual-consistency note and accepts healthy results or a safe degraded problem state.
2. Analytics and realtime views display bounded tables or empty states, generated time, and cache outcome.
3. Operations is read-only and does not expose raw DLQ payloads or secrets.

## Functional Requirements

- **FR-001**: The UI MUST provide dashboard, event generator, events, search, analytics, realtime, and operations views from a common responsive navigation.
- **FR-002**: Every API-backed view MUST show loading, empty, success, and actionable error states; errors MUST include status/detail/request ID when supplied.
- **FR-003**: Event generation MUST support one event and a bounded burst capped at 500 requests, pace request starts across five seconds, prevent overlapping submissions, and show visible progress plus 202/event ID/request ID or problem results.
- **FR-004**: Events MUST support user/event-type filters, cursor pagination, and expandable metadata rendered as formatted JSON.
- **FR-005**: Search MUST support a query and optional event type/user filters, display an eventual-consistency note, and handle 503 problem responses.
- **FR-006**: Analytics MUST support hour/day/week selection and display counts by event type; realtime MUST display generated time, totals, and X-Cache outcome.
- **FR-007**: Operations and dashboard MUST display only typed summaries from public endpoints and never raw credentials, request bodies, or DLQ payloads.
- **FR-008**: The app MUST use same-origin `/api/` requests through the local reverse proxy and remain usable at mobile and desktop widths with keyboard-accessible controls.
- **FR-009**: Docker Compose MUST serve the built UI alongside the API without requiring a separate development server.
- **FR-010**: UI contract tests MUST cover navigation, loading/error/empty states, bounded burst behavior, secret-safe rendering, and API request paths.

## Edge Cases

- API is unreachable at first load or between refreshes.
- Search projection is delayed or unavailable.
- Burst reaches the client cap or server rate limit.
- Metadata is malformed or too large for display.
- Empty event, search, analytics, realtime, queue, and DLQ results.

## Success Criteria

- **SC-001**: A reviewer can reach each required view from the navigation in at most two interactions.
- **SC-002**: Valid single-event submission shows the accepted event ID and request ID within two seconds after the response arrives.
- **SC-003**: Invalid and unavailable API paths show a visible, readable error with no uncaught browser error in the supported flow.
- **SC-004**: Burst generation never sends more than 500 requests from one user action, and the first through last request starts span approximately five seconds for bursts larger than one.
- **SC-005**: UI contract tests verify all required views and state transitions, and the Compose UI asset serves successfully through the documented port.

## Assumptions and Scope

- Authentication is not part of the current API contract.
- The UI is a reviewer console and does not become a source of platform truth.
- Existing public API contracts remain authoritative; no backend behavior is redefined here.
- Basic visual clarity and responsive behavior take priority over a design system.
