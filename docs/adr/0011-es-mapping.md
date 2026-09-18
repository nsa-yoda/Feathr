# ADR 0011: Use explicit ES mapping with flattened metadata plus derived full-text field

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Disable dynamic top-level mapping. Store metadata as `flattened` and derive `metadata_text` as analyzed `text`.

## Rationale

Flexible metadata can create mapping explosion if every user-controlled key becomes a field. `flattened` preserves shape for exact-like access while a derived text field meets the full-text requirement.

## Consequences

Projection code owns deterministic metadata flattening. Arbitrary client-provided Elasticsearch DSL is not exposed.
