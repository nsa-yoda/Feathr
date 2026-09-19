# ADR 0009: Use Redis token bucket with local degraded fallback

**Status:** Superseded by ADR 0010
**Date:** 2026-09-18


## Decision

Rate limiting is mandatory. Use an atomic Redis token bucket for distributed state. If Redis is unavailable, fall back to a stricter process-local token bucket.

## Rationale

Fail-open would turn a cache outage into an abuse-control outage; fail-closed would make Redis a total availability dependency. Local fallback balances protection and availability.

## Consequences

Fallback state is node-local and less globally precise, but the demo uses one node. Degraded limiter activation must be observable. Client IP extraction must respect trusted-proxy configuration.
