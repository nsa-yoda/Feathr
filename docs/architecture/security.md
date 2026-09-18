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
