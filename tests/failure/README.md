# Deterministic Failure and Recovery Tests

Feature 020 extends this selection with explicit fault seams and no external
service requirement. The 29-test failure gate proves:

- Mongo persistence retry, readiness impact, queue saturation, post-insert
  redelivery, and one-entry retry exhaustion DLQ disposition;
- Elasticsearch outage isolation, checkpoint ordering/recovery, and invalid
  resume history reconciliation;
- Redis realtime cache bypass and conservative local rate-limit fallback; and
- rebuild target failure and serving-alias safety.

Run `make test-failure` or `pytest -q tests/failure -m failure`. Missing or
unreachable real services are not needed for this deterministic selection;
Feature 019 records the separate real-service integration evidence.
