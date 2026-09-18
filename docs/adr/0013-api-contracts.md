# ADR 0013: Use keyset pagination and problem+json errors

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

List/search APIs use bounded cursor/search-after pagination. Errors use a consistent RFC 9457-style problem document with stable internal error codes and request IDs.

## Rationale

Offset pagination becomes expensive and unstable under concurrent writes. Consistent machine-readable errors improve maintainability and reviewer testing.

## Consequences

Cursors are opaque and versioned/validated. Do not expose stack traces or raw dependency exceptions.
