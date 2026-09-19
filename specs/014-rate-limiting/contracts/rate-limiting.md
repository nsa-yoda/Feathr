# Rate Limiting Contract

## Request admission

Middleware evaluates `RouteClass` and normalized identity before the handler. Exempt classes call through without a bucket. Admitted requests reserve a leaky-bucket release slot and asynchronously wait when necessary. Limited requests receive the standard rate headers; only full-backlog overflow receives `429` and `Retry-After`.

## Problem response

Full-backlog overflow uses the existing `application/problem+json` contract with a stable `error_code` (`rate_limit_exceeded`), request ID, and generic detail. The response never includes identity, Redis keys, or dependency errors.

## Configuration

Settings use `EVENT_PLATFORM_RATE_LIMIT_*` fields. Capacities describe reservation-backlog slots and refill values describe leak rates. Capacities, leak rates, costs, trusted proxy hops, and fallback entry cap are bounded; invalid settings produce the existing classified startup error.
