# Research: Event Query API

## Decisions

1. Keep query filtering and keyset predicates in `MongoEventStore.query()`; the API owns public parameter parsing and cursor encoding.
2. Use a signed versioned base64url token containing only UTC timestamp and UUID. HMAC validation prevents tamper and shape changes without exposing storage details.
3. Fetch one item beyond the requested page size to determine `next_cursor`, while the repository remains bounded by `limit + 1`.
4. Return canonical `CanonicalEvent` values directly through an API response model; Mongo's internal `_id` is never part of the model.
5. Resolve the store from application state so Feature 008 does not create unmanaged Mongo clients before lifecycle ownership is implemented.

## Rejected alternatives

- Offset pagination was rejected because concurrent inserts and large offsets create holes, duplicates, and poor query cost.
- Unsigned JSON cursors were rejected because clients could alter timestamp or ID continuation state.
- Elasticsearch-backed reads were rejected because canonical query results intentionally precede eventual search projection.
