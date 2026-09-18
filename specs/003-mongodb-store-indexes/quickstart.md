# Feature 003 Quickstart

1. Configure an async PyMongo client with a replica-set MongoDB URI.
2. Create `MongoEventStore(client[database]["events"])`.
3. Call `await store.ensure_indexes()` during an explicit dependency bootstrap.
4. Insert `CanonicalEvent` values, fetch by typed `UUID` (stored as a lowercase string), or call `query(EventQuery(...))`.
5. Pass only application-owned aggregation stages to `aggregate`; handle `MongoDependencyError` at the service boundary.

The repository remains constructible in unit tests without a running MongoDB instance.
