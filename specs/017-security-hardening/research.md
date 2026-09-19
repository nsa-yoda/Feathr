# Feature 017 Research

## Decisions

1. Enforce body size at ASGI receive time. `Content-Length` is an early rejection hint, while streamed chunks are counted because chunked requests may omit or falsify the header.
2. Return the existing RFC 9457-style problem shape for 413 and preserve request/operation IDs through the existing middleware boundary.
3. Use exact-origin CORS with no wildcard and no credentials by default. The UI origin is configuration, not source code.
4. Reuse the existing Pydantic query/domain models and cursor signatures. Security hardening adds missing control-character, size, and boundary tests instead of creating a second validation path.
5. Keep forwarding-header identity logic fail-closed at the direct peer unless a complete trusted chain is configured.
6. Add a small security-header middleware rather than coupling browser policy to individual routes.
7. Keep local Elasticsearch authentication disabled for the assessment's single-node demo, explicitly document the assumption, and avoid presenting it as production guidance.
8. Use non-root Python and nginx image users in image definitions. Compose orchestration remains Feature 021.

## Alternatives rejected

- Reading the entire body in a route dependency: parsing already occurred and memory may already be exhausted.
- Accepting `*` CORS with credentials: it defeats the explicit UI-origin boundary.
- Trusting the first `X-Forwarded-For` value: it permits client spoofing outside a verified proxy chain.
- Returning raw exception text for security diagnostics: it leaks dependency topology and credentials.
