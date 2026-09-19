# Research: ACR1 Storage Bootstrap Integrity

## Decision 1: Separate mutation from application startup

- **Decision**: Provide an idempotent `storage bootstrap` CLI command and make application startup verification-only.
- **Rationale**: Replicas must not race to mutate schema, while every process must still refuse unsafe storage before accepting traffic.
- **Alternatives considered**: Calling `ensure_indexes()` inside FastAPI lifespan was rejected because it mixes release migration ownership with replica startup. Manual shell commands without a typed verifier were rejected because drift would remain invisible to readiness.

## Decision 2: Use one immutable manifest and schema marker

- **Decision**: Define schema version 1 as a deterministic manifest of collection names and required indexes, record its fingerprint in a dedicated schema-state document, and verify both marker and live metadata.
- **Rationale**: A version alone cannot detect manual index drift; metadata alone cannot express application compatibility or migration ownership.
- **Alternatives considered**: A general migration framework was rejected as unnecessary for one additive schema version. Storing only a mutable latest-version integer was rejected because concurrent actors could conceal different manifests.

## Decision 3: Reuse event index declarations

- **Decision**: The storage manifest imports the existing `REQUIRED_INDEXES` event definitions.
- **Rationale**: This prevents a security and correctness sensitive uniqueness contract from being duplicated.
- **Alternatives considered**: Re-declaring event indexes in the bootstrap module was rejected because the two lists could drift.

## Decision 4: Index only observed operational access paths

- **Decision**: Add a unique checkpoint-projector index, a unique rebuild-ID index, a descending rebuild-started-at index, and declare the lease collection's built-in `_id_` index.
- **Rationale**: Current code performs checkpoint lookup/upsert by `projector`, rebuild updates by `rebuild_id`, latest-history lookup by `started_at`, and lease acquisition by a fixed `_id`.
- **Alternatives considered**: Indexing every rebuild phase/owner/expiry combination was rejected because no current query uses those paths and ADR 0010 prohibits speculative combinatorics.

## Decision 5: Fail startup before background work

- **Decision**: Verify storage after constructing the application-owned Mongo client and before search projector or persistence worker creation.
- **Rationale**: It preserves deterministic client cleanup while preventing ingestion from running without the uniqueness invariant.
- **Alternatives considered**: Readiness-only degradation was rejected because the queue could still accept events before the invariant existed.

## Decision 6: Preserve dependency injection tests

- **Decision**: Storage verification applies to a configured application-owned Mongo client. Tests or narrow applications using an injected typed store remain responsible for that store's invariant.
- **Rationale**: An injected port does not expose Mongo metadata and is used for isolated semantic tests.
- **Alternatives considered**: Extending every storage port with Mongo-specific verification was rejected because it leaks infrastructure into the domain boundary.
