# Feature Request: Demo / Operations UI

## Scope

A lightweight reviewer console, not a product frontend. React + TypeScript is preferred; keep dependencies modest. It must be included in Docker Compose.

## Pages

### Dashboard

Component health, queue visible/inflight/DLQ counts, worker state, Mongo event count if safely exposed, ES projection state/lag, realtime stats, cache status summary.

### Event Generator

Form for event type, timestamp/default-now, user ID, source URL, metadata JSON. Single submit and bounded burst-generation mode for demos. Show 202/event ID and validation/rate-limit/backpressure errors clearly.

### Events

Canonical event list with filters, cursor pagination, expandable formatted metadata.

### Search

Metadata full-text query, optional supported filters, paginated ES results, visible note that search is eventually consistent.

### Analytics

Hour/day/week selection and simple table/chart of counts by event type. Do not spend disproportionate time on visual polish.

### Realtime

Display rolling stats, generated time, and `X-Cache` outcome; allow manual refresh.

### Operations

Read-only component health, queue/retry/DLQ counts, projector checkpoint/lag, active/latest rebuild status. Do not expose secrets or raw DLQ payloads by default.

## Technical constraints

Use typed API client types derived manually or from OpenAPI if low friction. Handle loading/empty/error states. Reverse proxy to app where possible so local reviewer setup avoids broad CORS. Accessibility/basic responsive layout expected, but no elaborate design system.


## Dependencies

005, 008, 009, 011, 013, 015, 021

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
