# Recommended Initial Codex Prompt

Use this after running `scripts/bootstrap-speckit.sh`:

> Read `CODEX-HANDOFF.md`, `AGENTS.md`, `.specify/memory/constitution.md`, `ARCHITECTURE.md`, every accepted ADR, `specs/MASTER-SPEC.md`, and `specs/FEATURE-MANIFEST.yaml`. Treat locked architectural decisions as authoritative. Begin with Feature 001 only. Use `specs/001-platform-foundation/REQUEST.md` as the feature request and execute the full Codex-native Spec Kit production workflow: `$speckit-specify`, `$speckit-clarify`, `$speckit-plan`, `$speckit-checklist`, `$speckit-tasks`, `$speckit-analyze`, `$speckit-implement`, and `$speckit-converge` until clean. Then run the staff review and multi-agent review extensions, remediate findings, and update traceability/AI workflow evidence. Do not start later features until Feature 001 meets `docs/definition-of-done.md`. Continue in manifest dependency order unless a dependency-safe batching decision is explicitly documented.
