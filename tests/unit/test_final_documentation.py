"""Contract checks for the Feature 025 final documentation audit."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
README = ROOT / "README.md"
LOGO = ROOT / "logo.png"
ARCH = ROOT / "ARCHITECTURE.md"
TRACE = ROOT / "docs/requirements-traceability.md"
AI_LOG = ROOT / "docs/ai-workflow-log.md"
CHECKLIST = ROOT / "FINAL-ACCEPTANCE-CHECKLIST.md"


def test_readme_has_reviewer_workflow_and_ai_section() -> None:
    text = README.read_text()
    for section in (
        "## Configuration",
        "## Postman reviewer suite",
        "## AI in My Workflow",
        "## Reviewer UI and live Visualizer",
        "## Processing and consistency model",
        "## Testing and quality gates",
    ):
        assert section in text
    for command in (
        "make all",
        "make compose-config",
        "make smoke",
        "make postman",
        "make rebuild-status",
        "make rebuild-demo",
    ):
        assert command in text
    assert "not durable across catastrophic process loss" in text
    assert "Acceptance remained evidence-driven" in text
    assert "## Further documentation" in text
    assert "will also include" not in text


def test_readme_references_the_project_logo() -> None:
    text = README.read_text()
    assert LOGO.is_file()
    assert '<img src="logo.png"' in text


def test_architecture_preserves_canonical_and_runtime_boundaries() -> None:
    text = ARCH.read_text()
    for phrase in (
        "MongoDB:** authoritative event record",
        "Elasticsearch:** eventually consistent",
        "Redis:** disposable/derived cache",
        "202 Accepted",
        "not durable across application-process failure",
        "at-least-once",
        "Production SQS",
        "static reviewer console + nginx",
        "Failure modes",
        "scale projection",
        "Online Elasticsearch rebuild",
    ):
        assert phrase in text
    assert "React/TypeScript + nginx" not in text
    assert "static React build" not in text


def test_traceability_and_ai_log_have_concrete_final_entries() -> None:
    trace = TRACE.read_text()
    ai = AI_LOG.read_text()
    for feature in (
        "| Postman reviewer suite | 022",
        "| Demo operations UI | 023",
        "| Developer experience and CI | 024",
        "| AI in My Workflow | 025",
    ):
        assert feature in trace
    assert "TBD" not in trace
    for entry in ("Feature 021", "Feature 022", "Feature 023", "Feature 024", "Feature 025"):
        assert entry in ai
    assert "Serena MCP" in ai
    assert "Human decision and rationale" in ai
    for field in (
        "AI proposal/contribution",
        "What was useful",
        "Pushback/correction",
        "Artifacts/code affected",
        "Validation/review performed",
    ):
        assert field in ai[ai.rfind("### 2026-09-19 — Feature 025") :]
    tasks = (ROOT / "specs/025-final-documentation-ai-workflow/tasks.md").read_text()
    assert not re.search(r"- \[ \] T\d+", tasks)
    for path in (
        "README.md",
        "ARCHITECTURE.md",
        "docs/requirements-traceability.md",
        "docs/ai-workflow-log.md",
        "FINAL-ACCEPTANCE-CHECKLIST.md",
        "tests/unit/test_final_documentation.py",
        "specs/025-final-documentation-ai-workflow/reviews",
    ):
        assert (ROOT / path).exists(), path


def test_final_audit_rejects_unclassified_runtime_guarantees() -> None:
    implementation = "\n".join(
        path.read_text()
        for base in (ROOT / "src", ROOT / "tests")
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".py", ".md"} and path != Path(__file__)
    ).lower()
    assert "motor" not in implementation
    assert not re.search(
        r"exactly[- ]once (?:processing|delivery|guarantee|semantics)", implementation
    )

    governed = "\n".join(
        (ROOT / path).read_text().lower()
        for path in (
            "README.md",
            "ARCHITECTURE.md",
            "docs/requirements-traceability.md",
            "docs/ai-workflow-log.md",
        )
    )
    for phrase in (
        "exactly-once processing is guaranteed",
        "exactly-once guarantee",
        "202 accepted is durable",
        "durable 202 accepted",
    ):
        assert phrase not in governed
    assert not re.search(r"(?:elasticsearch|redis)\s+(?:is|remains)\s+authoritative", governed)


def test_final_checklist_records_static_completion_and_live_conditions() -> None:
    text = CHECKLIST.read_text()
    assert "## Evidence conditions" in text
    assert "Postman demo flow passes" in text
    assert "smoke test passes from clean stack" in text
    assert "- [x] README and ARCHITECTURE match code" in text
    assert "no positive exactly-once guarantee" in text
    assert "11 explicit service-gated skips" in text
    assert "online ES rebuild works" in text
