# Feature Request: Elasticsearch Mapping and Search API

## Mapping

Create explicit versioned index mapping with `dynamic:false`, stable keyword/date fields, `metadata` as `flattened`, and derived `metadata_text` as analyzed `text` using standard+lowercase+asciifolding. Search alias is `events-search` (configurable prefix allowed).

## Projection transform

Recursively flatten metadata keys/scalar values into deterministic searchable text while preserving original bounded metadata in the flattened field. Handle arrays/nulls consistently. Never create dynamic fields from metadata keys.

## Endpoint

`GET /events/search` performs full-text search across `metadata_text`. It may also support stable exact filters (type/user/date) but must not accept arbitrary Elasticsearch JSON DSL from clients.

## Pagination

Bounded page size and `search_after` cursor with deterministic sort, typically timestamp desc + event_id desc.

## Dependency failure

If ES is unavailable return a clear 503 problem response. Do not silently substitute a different Mongo search behavior.

## Tests

Mapping assertion, metadata term search, case/diacritic behavior, nested metadata text extraction, search pagination, unsafe/oversized query rejection.


## Dependencies

002, 010

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
