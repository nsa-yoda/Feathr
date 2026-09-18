# Failure Drill Guide

Feature 020 should automate deterministic tests, but the finished README may also show manual demo drills:

- stop/pause Elasticsearch: ingestion and Mongo query remain healthy; search degrades;
- stop Redis: realtime returns BYPASS; rate limiter reports local fallback;
- stop Mongo: readiness fails; worker retries; queue depth grows and eventually applies backpressure;
- recover each dependency and observe service/component recovery.

Manual drills must never be the only proof; pytest failure tests remain authoritative.
