# Feature Request: Security Hardening

## Required controls

- request body max size enforced before unbounded parse;
- metadata bounds from Feature 002;
- search query length/character safety and generated DSL only;
- cursor size/schema validation;
- date range/page size limits;
- explicit CORS limited to the configured UI origin;
- trusted proxy handling disabled by default;
- secrets via env/settings, sanitized config logging;
- safe dependency timeouts;
- non-root application/UI containers;
- no debug stack traces in normal API errors;
- security-sensitive headers appropriate to API/UI where practical.

## Local dependencies

If Elasticsearch security is disabled for local single-node simplicity, document this as local-only. Do not present it as a production recommendation.

## Tests

Oversized body/query/cursor; CORS allowed/denied origin; forwarding-header spoof; error redaction; metadata abuse cases.


## Dependencies

002, 005, 008, 011, 014, 015

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
