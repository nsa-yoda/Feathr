# Implementation Plan: ACR1 CI and Supply Chain Hygiene

## Summary

Add explicit CI/local gates that distinguish optional service-gated integration runs from mandatory configured integration runs, and inspect tracked source archives for caches/platform debris and required source/spec/lock files.

## Design

- `make test-integration-required` requires Mongo, Elasticsearch, and Redis endpoint variables and fails if the JUnit report contains skips.
- `make check-source-archive` rejects tracked caches/bytecode/platform metadata and verifies core archive inputs.
- CI runs archive validation alongside locked static/test gates.
