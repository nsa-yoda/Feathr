# Assumptions and Explicit Interpretations

1. The assignment intentionally mandates an in-process queue. We will not hide its durability/scaling limitations behind claims that belong to SQS.
2. Events are append-only for this assessment. No event update/delete API is required.
3. `source_url` filtering means exact normalized URL matching in Mongo; metadata free-text belongs to Elasticsearch.
4. All persisted times are UTC. Producer timestamps must contain an offset or be rejected; naive datetimes are not silently guessed.
5. Week buckets use ISO week semantics in UTC unless the final API contract deliberately exposes timezone configuration.
6. Arbitrary metadata is JSON-compatible, but bounded by size, nesting depth, key count, and scalar/list constraints for abuse resistance.
7. Search can lag canonical reads. Integration tests must poll eventual conditions with deadlines.
8. The local stack is for evaluation and disables/relaxes some dependency-level security that would be mandatory in a production network. This does not justify weak application input/security behavior.
9. No user authentication model exists in the brief. Client IP is therefore the available rate-limit identity for the assessment.
10. The reviewer UI is supplemental and must not introduce a new source of truth.
