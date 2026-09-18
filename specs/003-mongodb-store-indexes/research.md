# Feature 003 Research

## Decisions

- Use `pymongo.AsyncMongoClient` and `AsyncCollection`; Motor is explicitly out of scope.
- Store UUID event IDs as lowercase strings. This avoids driver codec configuration and keeps Mongo, API, and projection identifiers identical.
- Keep repository query inputs typed and small. The API owns opaque cursor encoding; the repository owns the exclusive timestamp/ID predicate.
- Use named `IndexModel` definitions and `create_indexes`; repeated bootstrap is safe because names and keys are stable.
- Catch `PyMongoError` at the adapter boundary and expose `MongoDependencyError` or `EventAlreadyExists` only.

## Index rationale

The event ID index is unique for duplicate resolution. The four compound indexes match known access paths and place the range/tie-break fields in query order. Metadata and wildcard indexes are deliberately omitted because Elasticsearch owns metadata search and broad indexes increase write cost.

## Rejected alternatives

- Motor: rejected by the locked request.
- Raw collection injection into routes: rejected because it couples HTTP code to storage and leaks driver errors.
- UUID BSON subtype configuration: rejected for this feature because string IDs are portable and deterministic.
