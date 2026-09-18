# Definition of Done

A feature is done only when all applicable items are true:

- Spec Kit `spec.md`, `plan.md`, checklist(s), and `tasks.md` exist and agree.
- `$speckit-analyze` has no unresolved critical consistency issue.
- all planned code and tests are implemented;
- feature tests pass;
- format/lint/type checks pass for touched code;
- meaningful error/failure paths are tested;
- logging/metrics are included for operationally meaningful behavior;
- docs/API examples are updated;
- `$speckit-converge` reports no remaining work (or adds no new tasks after the final iteration);
- `$speckit-staff-review-run` has no unresolved Blocker;
- `$speckit-review-run all` has no unresolved Critical issue;
- Important/Warning issues are fixed unless a written rationale is recorded in the feature review folder;
- no new unbounded input, unbounded retry, unbounded concurrency, or unbounded cardinality is introduced;
- requirements traceability and AI workflow log are updated when relevant.

Repository completion additionally requires successful Compose smoke, Postman run, unit/integration/failure suites, and documentation reconciliation.
