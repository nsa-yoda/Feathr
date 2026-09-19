# Security and Abuse-Resistance Model

This assessment has no end-user authentication requirement, so the security focus is robust input handling and service abuse prevention.

- mandatory rate limiting with Redis + local fallback;
- bounded body size and metadata depth/size;
- strict URL/timestamp/string validation;
- safe full-text query construction; never pass arbitrary raw query DSL from clients;
- no dynamic ES mapping from untrusted metadata;
- cursor tokens are opaque and validated/signed or safely encoded with strict schema;
- no trust of forwarding headers by default;
- explicit CORS origin for the demo UI;
- local Compose credentials are configuration, not production recommendations;
- non-root containers where feasible;
- dependency versions pinned/locked;
- no sensitive payloads in normal logs.

## Feature 017 enforcement

The API applies a receive-time request body limit before FastAPI parses JSON. The
default is 1 MiB, configurable through `EVENT_PLATFORM_REQUEST_BODY_MAX_BYTES`
within a 1 KiB–16 MiB range; declared `Content-Length` and streamed chunks are
both checked. Feature 002 remains the authority for metadata depth, key count,
string/list, numeric, and serialized-size limits.

The raw query string is bounded at 8 KiB by default (configurable from 256 bytes
to 64 KiB) before route parsing and returns a safe 414 when the limit is exceeded.

Search and canonical query inputs use bounded typed models and signed opaque
cursors. Search builds a fixed query and never accepts client Elasticsearch DSL.
Search and query date ranges are UTC and bounded to 366 days; page sizes and
cursor tokens are bounded at the route and model boundaries.

CORS is disabled unless `EVENT_PLATFORM_CORS_ALLOWED_ORIGIN` is set to one exact
HTTP(S) origin. Wildcards, credentials, paths, and userinfo are rejected. The
default trusted proxy hop count is zero, so `X-Forwarded-For` does not change
rate-limit identity unless a complete trusted chain is configured.

Responses carry `nosniff`, `DENY` framing, `no-referrer`, and a restrictive
content security policy. Dependency clients receive bounded timeout settings.
Application and UI image definitions run as non-root users. Local Compose may
run Elasticsearch without authentication for the single-node demonstration;
that is a local convenience and is not a production security recommendation.
