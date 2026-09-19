# Feature 018 Data Model

## Semantic test evidence

| Field | Meaning | Constraint |
| --- | --- | --- |
| `focus_area` | Queue, worker, query, search, analytics, cache, rate-limit, or settings boundary | Must map to a requirement in `spec.md` |
| `fixture` | Fake dependency, state setup, and deterministic clock | Must not require an external service or wall-clock sleep |
| `action` | Public function, route, or state transition under test | Must exercise behavior rather than only a mock call |
| `assertion` | Observable response, state, error classification, or downstream-call count | Must cover success, boundary, or failure semantics |

## Coverage report

| Field | Meaning | Constraint |
| --- | --- | --- |
| `source_root` | Measured application package | `src/event_platform` |
| `test_root` | Executed isolated tests | `tests/unit` |
| `format` | Human and machine report | Terminal summary and XML file under `coverage/` |
| `measurement` | Observed line/branch execution | Reported only after the command runs; no fixed target in this feature |
