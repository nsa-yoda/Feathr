# Feature Request: Developer Experience and CI

## Local commands

Provide a simple Makefile/just/task interface for format, lint, typecheck, unit, integration, failure, all tests, compose up/down/reset, smoke, Postman run, and search rebuild CLI demonstration.

## CI

GitHub Actions (or equivalent repository CI) should at minimum run formatting/lint/type checks, unit tests, and a realistic integration job with service containers/Compose if feasible. Cache dependencies without sacrificing reproducibility.

## Reproducibility

Commit lockfiles. Pin major dependency/runtime versions. Verify Docker Compose config. Avoid hidden host dependencies beyond Docker + standard developer tools documented in README.

## Quality artifact

CI should make failures easy to diagnose and may publish coverage/test reports. Do not build a giant pipeline unrelated to the assessment.


## Dependencies

018, 019, 020, 021

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
