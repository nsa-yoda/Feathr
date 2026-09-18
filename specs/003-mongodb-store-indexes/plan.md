# Implementation Plan: MongoDB Store and Indexes

**Branch**: `003-mongodb-store-indexes` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Add a typed PyMongo Async repository for canonical events, deterministic query predicates, safe BSON mapping, exception translation, and idempotent required-index bootstrap. Keep Mongo optional at foundation startup until a later feature wires it into application lifespan.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependency**: PyMongo 4.x Async API  
**Testing**: pytest unit tests plus real-Mongo integration tests gated by `MONGO_URI`  
**Constraints**: no Motor, no raw collection from routes, no metadata/wildcard index, no raw driver errors

## Constitution Check

- Typed boundaries: **PASS** — repository values and errors are explicit.
- Canonical ownership: **PASS** — Mongo is the only canonical store.
- Async I/O: **PASS** — all driver calls use awaitable PyMongo Async methods.
- Error handling: **PASS** — PyMongo errors are classified at the adapter boundary.
- Testing: **PASS** — pure mapping tests and real-Mongo integration coverage are planned.

## Design

1. `MongoEventStore` accepts an async collection and owns serialization, filters, and driver calls.
2. `EventQuery` validates page size, filter lengths, and the 366-day date-range bound, then constructs a deterministic descending Mongo predicate. Feature 008 owns opaque cursor encoding and public endpoint defaults.
3. Named `IndexModel` values define the five required indexes; bootstrap returns names after `create_indexes`.
4. Integration tests use a dedicated collection and skip only when `MONGO_URI` is absent.
