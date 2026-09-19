# Implementation Plan: MongoDB Analytics

**Branch**: `009-mongodb-analytics` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Add a typed `GET /events/stats` route that validates a bounded UTC range, builds a Mongo `$match`/`$dateTrunc`/`$group`/`$sort`/bounded-result pipeline, executes it through Feature 003's async repository, and returns self-describing ordered points without partial truncation.

## Technical Context

**Language/Version**: Python 3.13 runtime; Python 3.12+ contract  
**Primary Dependencies**: FastAPI, Pydantic v2, PyMongo Async repository boundary  
**Storage**: Feature 003 Mongo canonical events  
**Testing**: pytest, pytest-asyncio, FastAPI TestClient, fake repository, real Mongo integration  
**Constraints**: UTC only, inclusive ranges, 366-day bound, maximum 10,000 grouped points, no raw-event Python aggregation, safe errors  

## Constitution Check

- Mongo remains canonical; analytics does not read Elasticsearch or Redis.
- The async repository boundary owns driver interaction and translates driver failures.
- Input and output models are typed and bounded.
- Tests cover boundaries and a real Mongo aggregation lifecycle when `MONGO_URI` is available.

## Project Structure

```text
src/event_platform/api/routes/stats.py             # range model, pipeline builder, GET /events/stats
src/event_platform/main.py                         # include analytics router
tests/unit/test_mongodb_analytics.py               # route, pipeline, validation, safe failures
tests/integration/test_mongodb_analytics_integration.py # real Mongo dateTrunc boundaries
docs/api-contract.md                                # stats contract guardrail
docs/requirements-traceability.md                   # feature evidence
```

## Phases

1. Define range/point/response models and deterministic pipeline builder.
2. Add route wiring and safe storage/decode error mapping.
3. Add unit and real Mongo integration coverage for all buckets and boundaries.
4. Update documentation, converge, review, and run final quality gates.
