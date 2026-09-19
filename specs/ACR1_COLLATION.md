# ACR1 Code Review Collation

This document maps the findings in `AUTO_CODE_REVIEW_1.md` and `AUTO_CODE_REVIEW_1_B.md` to the additional ACR1 specification set. Findings were grouped by implementation ownership and invariant, rather than copied into one spec per review bullet.

## Finding Map

| ACR1 feature | AUTO_CODE_REVIEW_1.md | AUTO_CODE_REVIEW_1_B.md |
|---|---|---|
| 026 storage bootstrap integrity | P1-001, P2-004 | P0-01, P1-14, P2-02, P2-04, P2-13 |
| 027 lifecycle delivery safety | P1-003 | P0-02, P1-04, P2-09 |
| 028 rebuild convergence operations | P1-002, P2-001 | P1-12, P1-13, P2-01, P2-10, P2-11 |
| 029 projection resilience ownership | — | P1-02, P1-03, P1-06, P3-03 |
| 030 request idempotency | — | P1-05, P2-03 |
| 031 cursor API boundary hardening | P2-004 | P1-01, P2-03, P2-08, P2-12, P3-01, P3-02 |
| 032 queue performance durability | P2-003 | P0-04, P1-07 |
| 033 analytics cache scalability | P2-004 | P1-08, P1-09, P2-04 |
| 034 route observability consistency | P2-002 | P1-10, P2-05, P2-06, P3-05 |
| 035 composition dependency typing | P3-001, P3-002 | P2-15, P3-04 |
| 036 CI supply chain hygiene | P2-007 | P2-07, P2-14, redundancy log |
| 037 production security boundary | P2-006, P3-004 | P0-03, P1-11, P2-06, P3-06 |

## Collation Decisions

- Review severities were normalized against the repository constitution and delivery profile. Production findings become requirements of the production profile without rewriting the accepted local demo guarantees.
- Durable broker adoption is specified as a production adapter and migration path. The in-process queue remains available for deterministic local development with its volatile guarantee reported truthfully.
- Authentication, tenant authorization, TLS, secrets, operational endpoint access, and replica-aware degraded limiting are one production security boundary because they depend on the same caller and deployment identity model.
- Rebuild boundary races, fencing, convergence, cleanup, status, history, and operator controls are one lifecycle because they share a lease and state-machine invariant.
- Duplicate cursor codecs, secret rotation, DTO leakage, URL credentials, time normalization, and bounded reads are combined at the public API trust boundary.
- AppleDouble files, cache output, stale scripts, compatibility shims, and empty placeholder packages are handled by repository-hygiene acceptance rules rather than deletion instructions without consumer verification.

## Already Resolved During Review Follow-up

- The dashboard refresh retry defect from `AUTO_CODE_REVIEW_1.md` P2-005 already has an implementation fix and regression coverage, so no duplicate ACR1 feature was created.
- The missing frontend behavior-test observation from `AUTO_CODE_REVIEW_1.md` P3-003 is covered by the existing dashboard test harness and the refresh regression coverage; broader CI execution guarantees are captured in feature 036.

## Coverage Rule

Every actionable finding in either review is mapped above, explicitly recorded as already resolved, or represented by the repository-hygiene rules. Implementation planning must retain the source-finding references so later convergence can prove disposition without rereading both reviews.
