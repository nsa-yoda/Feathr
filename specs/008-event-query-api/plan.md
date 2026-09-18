# Implementation Plan: Event Query API

**Branch**: `008-event-query-api` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Add a typed `GET /events` route that validates bounded filters, decodes/encodes signed versioned keyset cursors, queries the Feature 003 canonical Mongo store, and returns canonical event pages with safe problem responses. Keep Mongo client lifecycle outside this feature and expose a 503 when the store is not available.

## Technical Context

**Language/Version**: Python 3.13 runtime; Python 3.12+ contract
**Primary Dependencies**: FastAPI, Pydantic v2, PyMongo Async repository boundary, HMAC/base64
**Storage**: Feature 003 Mongo canonical events
**Testing**: pytest, pytest-asyncio, FastAPI TestClient, fake query store
**Target Platform**: Linux-compatible async service
**Project Type**: FastAPI async web service
**Performance Goals**: bounded page reads and one extra item for continuation detection
**Constraints**: no blocking I/O, no unbounded cursor/input, no raw Mongo IDs/errors, descending keyset semantics
**Scale/Scope**: pages of 1–200 events per request

## Constitution Check

- Mongo remains canonical and Elasticsearch is not used in this route.
- Cursor pagination is bounded and tamper-validated.
- Async repository calls remain behind `MongoEventStore`; no client is created at import time.
- Problem responses remain safe and use request correlation IDs.
- Tests cover behavior and failure paths without arbitrary sleeps.

## Project Structure

```text
src/event_platform/api/routes/query.py      # cursor codec, query models, GET /events
src/event_platform/api/routes/__init__.py   # route package
src/event_platform/main.py                  # include query router
tests/unit/test_event_query_api.py          # filters, pagination, cursor/error behavior
docs/api-contract.md                         # GET /events evidence
```

**Structure Decision**: Keep route/cursor concerns separate from the ingestion route and reuse the typed storage repository for all canonical reads.

## Complexity Tracking

No constitution violations.
