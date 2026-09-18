# Requirements Traceability Matrix

This file starts as a planning matrix. Codex must update the final two columns with concrete source/test evidence as implementation lands.

| Requirement | Feature(s) | Planned evidence | Implementation evidence | Test evidence |
|---|---|---|---|---|
| POST /events validates and enqueues asynchronously | 002, 004, 005 | API spec + queue contract | TBD | TBD |
| Background worker persists Mongo | 005, 006 | worker/repository | TBD | TBD |
| Retry with backoff | 007 | retry policy | TBD | TBD |
| GET /events filters | 009 | query service | TBD | TBD |
| GET /events/stats aggregation | 010 | Mongo pipeline | TBD | TBD |
| GET /events/search metadata full-text | 011, 012 | ES projection/search | TBD | TBD |
| GET /events/stats/realtime Redis cache | 014 | cache-aside service | TBD | TBD |
| Mongo indexes | 003 | index bootstrap | TBD | TBD |
| ES mapping/analyzers | 012 | versioned mapping | TBD | TBD |
| ARCHITECTURE.md standalone | 025 | root architecture | `ARCHITECTURE.md` | doc review |
| Failure modes | 005, 011, 014, 016, 021, 025 | failure docs/tests | TBD | TBD |
| Scaling considerations | 025 | architecture | `ARCHITECTURE.md` | doc review |
| What changes in production | 004, 013, 025 | SQS/rebuild/scaling docs | TBD | doc review |
| Unit tests | all + 019 | per-feature tests | TBD | TBD |
| 2+ integration lifecycles | 020 | real-service tests | TBD | TBD |
| Clear module boundaries | 001 | package architecture | TBD | review |
| Meaningful error handling/logging | 016, 018 | problem+json + JSON logs | TBD | TBD |
| AI in My Workflow | 025 | maintained workflow log | TBD | doc review |
| Dockerfile/docker-compose bonus | 022 | full stack | TBD | smoke |
| Rate limiting bonus (mandatory here) | 015 | distributed + fallback limiter | TBD | TBD |
| Event deduplication bonus | 006 | unique ID/payload hash | TBD | TBD |
| DLQ simulation bonus | 007 | local redrive | TBD | TBD |
| AWS SQS drop-in notes | 004, 025 | port + design notes | TBD | doc review |
| Reviewer UI value-add | 024 | Compose UI | TBD | browser/smoke |
| Postman reviewer suite value-add | 023 | collection/environment | TBD | Newman/Postman run |
