# Spec Kit + Review Workflow

This project intentionally uses the full production SDD path rather than the short path.

## Core Spec Kit

Codex integration installs skills under `.agents/skills` and uses `$speckit-<command>` invocation. For each feature:

```text
$speckit-specify
$speckit-clarify
$speckit-plan
$speckit-checklist
$speckit-tasks
$speckit-analyze
$speckit-implement
$speckit-converge
```

Converge is append-only against `tasks.md`; if it adds work, implement and converge again.

## Staff Review

The installed `staff-review` extension defines `speckit.staff-review.run`. Under Codex skills syntax this should surface as the equivalent `$speckit-staff-review-run` skill. Run it after implementation/convergence with focus areas when useful.

It validates implementation against the feature spec and checks security, performance, error handling, and test coverage, writing structured review output to the feature review area.

## Multi-agent Review

The `review` extension defines `speckit.review.run` and six focused reviewers: code, comments, tests, errors, types, simplify. Under Codex skills syntax the coordinator should surface as `$speckit-review-run`.

Run the complete suite for acceptance. During remediation, use targeted aspects to reduce noise, e.g. code/errors or tests/types, then rerun the complete suite before final repository handoff when practical.

## Gate policy

- staff-review Blocker: must fix;
- review Critical: must fix;
- Warning/Important: fix by default; document the reason if intentionally accepted;
- Suggestions: apply when they improve clarity/correctness without scope creep.

The purpose is not to blindly satisfy every AI comment. Exercise engineering judgment and log meaningful pushback in `docs/ai-workflow-log.md`.
