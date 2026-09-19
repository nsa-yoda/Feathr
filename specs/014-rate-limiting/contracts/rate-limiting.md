# Rate Limiting Contract

## Request admission

Middleware evaluates `RouteClass` and normalized identity before the handler. Exempt classes call through without a bucket. Limited requests receive the four standard rate headers; denied requests receive `429` and `Retry-After`.

## Problem response

Denial uses the existing `application/problem+json` contract with a stable `error_code` (`rate_limit_exceeded`), request ID, and generic detail. The response never includes identity, Redis keys, or dependency errors.

## Configuration

Settings use `EVENT_PLATFORM_RATE_LIMIT_*` fields. Capacities, refill rates, costs, trusted proxy hops, and fallback entry cap are bounded; invalid settings produce the existing classified startup error.
