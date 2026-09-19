# Feature 009 Research

## Decisions

1. Keep aggregation pipeline construction in the API route module and execute it through `MongoEventStore.aggregate()`; the route does not access a driver collection.
2. Use a fixed UTC timezone and Monday week boundaries. A future feature may add configured timezones after defining DST semantics.
3. Use an inclusive `$gte`/`$lte` timestamp match before `$dateTrunc`, `$group`, and `$sort`.
4. Default both omitted dates to a 24-hour window ending at an injectable UTC clock. Partial ranges are rejected to avoid surprising effective windows.
5. Return only nonzero Mongo group rows. Synthesizing empty buckets would require a separate calendar pipeline and is outside this feature.
6. Translate malformed aggregation documents to `MongoDependencyError("decode_analytics")` so driver and decode failures share the safe 503 boundary.

## Rejected Alternatives

- Loading canonical events into Python and counting them was rejected because it violates the pipeline requirement and scales with raw history.
- Elasticsearch or Redis reads were rejected because Mongo is canonical and derived stores are eventual/non-authoritative.
- Client-selected timezones were deferred because DST and week semantics need a separate accepted contract.
