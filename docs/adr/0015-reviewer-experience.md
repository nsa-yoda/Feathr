# ADR 0015: Include Dockerized demo UI and executable Postman suite

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Ship a lightweight React/TypeScript operations console and a Postman collection/environment with assertions. Include both in the normal Compose/reviewer workflow.

## Rationale

They do not earn backend points directly, but they drastically reduce friction for the engineering panel and make async/cache/failure behavior easy to demonstrate.

## Consequences

UI scope remains intentionally narrow. Backend APIs and pytest remain authoritative; the UI never becomes a hidden dependency.
