# Feature 005 Research

- FastAPI request models reuse the pure Feature 002 `EventInput` contract.
- The route owns validation and hands a JSON-safe `CanonicalEvent` envelope to the Feature 004 queue.
- Feature 006 owns durable duplicate conflict semantics; this route only hashes the optional idempotency key.
- Existing request-ID middleware and safe problem handlers provide response correlation and generic 503 details.
