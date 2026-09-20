# Research

The prior `Idempotency-Key` behavior only hashed the key into each event. It could not replay an API outcome or coordinate concurrent requests. A small registry boundary fits the existing Mongo canonical store and avoids conflating request retries with global event payload deduplication.
