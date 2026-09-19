# Implementation Plan: Security Hardening

**Branch**: `017-security-hardening` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-security-hardening/spec.md`

## Summary

Harden the existing FastAPI boundary with receive-time body limits, exact-origin CORS, safe security headers, validated timeout/origin settings, strict query/cursor checks, safe diagnostics, and non-root image definitions. Preserve the existing typed domain/query/search validation and rate-limit trust model.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI/Starlette, Pydantic v2, existing async MongoDB/Elasticsearch/Redis clients, pytest

**Storage**: No new storage; Mongo remains canonical and derived services remain bounded dependencies.

**Testing**: pytest unit/failure tests, static checks, source-level container assertions, optional real-service integration.

**Target Platform**: Linux single-process API and reviewer UI containers.

**Project Type**: Async web service with a later static UI container.

**Performance Goals**: Reject oversized bodies from the receive path without buffering beyond the configured limit; keep security middleware O(request bytes) and query validation bounded.

**Constraints**: No raw request body/secret logs, no arbitrary Elasticsearch DSL, exact CORS origin, trusted proxy disabled by default, no unbounded parse or timeout.

**Scale/Scope**: One demo API process, bounded requests up to 16 MiB, existing route/query limits, one explicitly configured browser origin.

## Constitution Check

- **V. Security and abuse resistance**: PASS — body, metadata, query, cursor, CORS, proxy, secret, and container controls are explicit and tested.
- **VI. Async correctness**: PASS — receive wrappers and async clients do not block the event loop; timeouts are bounded.
- **VII. Observability**: PASS — rejection and dependency failures use existing safe structured logging and problem responses.
- **VIII. Testing**: PASS — abuse and failure paths receive deterministic regression coverage.
- **IX. Spec-first discipline**: PASS — this plan follows the accepted security spec and generated task list.

## Project Structure

```text
src/event_platform/
├── api/middleware/body_limit.py
├── api/middleware/security_headers.py
├── core/settings.py
├── main.py
└── search/search.py, api/routes/query.py, api/routes/search.py
tests/unit/test_security_hardening.py
tests/failure/test_security_failure.py
Dockerfile
frontend/Dockerfile
docs/architecture/security.md
docs/api-contract.md
```

**Structure Decision**: Keep security enforcement at the HTTP/configuration boundary and reuse existing typed domain/search models. Image definitions are minimal and do not introduce Compose orchestration before Feature 021.

## Complexity Tracking

No constitution violations. The receive wrapper and security-header middleware are two small cross-cutting modules because route-local validation cannot enforce pre-parse body limits or guarantee consistent response headers.
