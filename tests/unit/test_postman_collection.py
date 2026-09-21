"""Docker-free contract tests for the Feature 022 Postman assets."""

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
COLLECTION = ROOT / "postman/Distributed Event Processing Platform.postman_collection.json"
ENVIRONMENT = ROOT / "postman/Local Docker.postman_environment.json"
ENVIRONMENT_TEMPLATE = ROOT / "postman/Local Docker.postman_environment.template.json"
RUNNER = ROOT / "scripts/postman"
PACKAGE = ROOT / "tools/postman/package.json"
PACKAGE_LOCK = ROOT / "tools/postman/package-lock.json"

EXPECTED_FOLDERS = [
    "00 Environment Verification",
    "01 Event Ingestion",
    "02 Idempotency Dedup",
    "03 Event Queries",
    "04 Analytics",
    "05 Elasticsearch Search",
    "06 Realtime Cache",
    "07 Validation & Errors",
    "08 Rate Limiting",
    "09 Failure & Dependency-visible",
    "10 Health & Readiness",
    "11 End-to-End Demo Scenario",
]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value


def _requests(item: dict[str, Any]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for child in item.get("item", []):
        if "request" in child:
            requests.append(child)
        else:
            requests.extend(_requests(child))
    return requests


def _script_text(request: dict[str, Any]) -> str:
    return "\n".join(
        line
        for event in request.get("event", [])
        for line in event.get("script", {}).get("exec", [])
    )


def test_collection_is_v21_with_required_folder_order_and_requests() -> None:
    collection = _load(COLLECTION)
    assert collection["info"]["schema"].endswith("collection/v2.1.0/collection.json")
    folders = collection["item"]
    assert [folder["name"] for folder in folders] == EXPECTED_FOLDERS
    assert all(_requests(folder) for folder in folders)
    requests = _requests(collection)
    assert len(requests) >= 19
    for request in requests:
        text = _script_text(request)
        assert "pm.test" in text
        assert "pm.response.code" in text or "response.code" in text


def test_collection_captures_identity_and_polls_with_deadlines() -> None:
    collection = _load(COLLECTION)
    requests = _requests(collection)
    text = "\n".join(_script_text(request) for request in requests)
    for variable in ("eventId", "requestId", "eventUserId", "idempotencyKey", "nextCursor"):
        assert variable in text
    assert "duplicateEventId" in text
    assert "Date.now()" in text
    assert "pollDeadlineMs" in text
    assert "pollRequestTimeoutMs" in text
    assert text.count('pm.environment.get("pollRequestTimeoutMs")') >= 3
    assert "setTimeout(poll, interval)" in text
    assert "sleep " not in text


def test_collection_covers_required_statuses_and_safe_problem_contract() -> None:
    collection = _load(COLLECTION)
    requests = _requests(collection)
    text = "\n".join(_script_text(request) for request in requests)
    urls = "\n".join(str(request["request"]["url"]) for request in requests)
    for status in ("202", "422", "429", "503"):
        assert status in text
    for field in ("status", "detail", "error_code", "request_id", "Retry-After"):
        assert field in text
    assert "rateLimitBurst" in text
    burst = next(
        request
        for request in requests
        if request["name"] == "Bounded admission burst drains without rejection"
    )
    burst_text = _script_text(burst)
    assert "completed === burst" in burst_text
    assert "response.code !== 200" in burst_text
    assert "Math.max" in burst_text and "10000" in burst_text
    readiness = next(request for request in requests if request["name"] == "Readiness contract")
    assert "persistence_worker" in _script_text(readiness)
    targeted = {request["name"]: _script_text(request) for request in requests}
    assert "pm.response.code).to.eql(202)" in targeted["Ingest event"]
    assert "pm.response.code).to.eql(422)" in targeted["Invalid cursor"]
    assert "pm.response.code).to.eql(422)" in targeted["Invalid event body"]
    assert "body.request_id" in targeted["Search dependency-visible response"]
    assert 'body.by_event_type["postman.demo"]' in targeted["Realtime statistics"]
    assert "setTimeout(pollRealtime, interval)" in targeted["Realtime statistics"]
    assert "pollDeadlineMs" in targeted["Realtime statistics"]
    assert "setTimeout(pollRealtime, interval)" in targeted["Realtime statistics repeat"]
    assert "pollDeadlineMs" in targeted["Realtime statistics repeat"]
    assert "setTimeout(pollRealtime, interval)" in targeted["Demo realtime statistics"]
    assert "body.components.persistence_worker" in targeted["Readiness contract"]
    for endpoint in (
        "/events",
        "/events/search",
        "/events/stats",
        "/events/stats/realtime",
        "/metrics",
    ):
        assert endpoint in urls
    demo = next(
        folder for folder in collection["item"] if folder["name"] == "11 End-to-End Demo Scenario"
    )
    demo_names = {request["name"] for request in _requests(demo)}
    assert {
        "Demo canonical event",
        "Demo search evidence",
        "Demo realtime statistics",
        "Demo metrics",
    } <= demo_names


def test_environment_is_non_secret_and_matches_template() -> None:
    environment = _load(ENVIRONMENT)
    template = _load(ENVIRONMENT_TEMPLATE)
    values = {entry["key"]: entry["value"] for entry in environment["values"]}
    template_values = {entry["key"]: entry["value"] for entry in template["values"]}
    assert values["baseUrl"] == "http://localhost:8000"
    assert values["pollDeadlineMs"] == "30000"
    assert values["pollIntervalMs"] == "250"
    assert values["pollRequestTimeoutMs"] == "5000"
    assert values["rateLimitBurst"] == "100"
    assert values.keys() == template_values.keys()
    assert not any("password" in key.lower() or "token" in key.lower() for key in values)


def _run_runner(path: Path, *, fake_newman: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if fake_newman is None:
        env["POSTMAN_AUTO_INSTALL"] = "0"
        env["NEWMAN_BIN"] = str(path / "missing-newman")
    else:
        bin_dir = path / "bin"
        bin_dir.mkdir(parents=True)
        executable = bin_dir / "newman"
        script = (
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" > '{path / 'args.txt'}'\n"
            f"exit {fake_newman}\n"
        )
        executable.write_text(script)
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        env["NEWMAN_BIN"] = str(executable)
    return subprocess.run(
        ["bash", str(RUNNER), "--bail"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_newman_wrapper_controls_missing_and_propagates_exit_code(tmp_path: Path) -> None:
    missing = _run_runner(tmp_path)
    assert missing.returncode == 2
    assert "Newman" in missing.stderr
    success = _run_runner(tmp_path / "success", fake_newman="0")
    assert success.returncode == 0
    assert (
        "Distributed Event Processing Platform.postman_collection.json"
        in (tmp_path / "success/args.txt").read_text()
    )
    failure = _run_runner(tmp_path / "failure", fake_newman="7")
    assert failure.returncode == 7


def test_newman_wrapper_reports_missing_assets(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["POSTMAN_ROOT"] = str(tmp_path)
    env["POSTMAN_AUTO_INSTALL"] = "0"
    result = subprocess.run(
        ["bash", str(RUNNER)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "missing" in result.stderr


def test_newman_runtime_is_repository_managed_and_exactly_locked() -> None:
    package = _load(PACKAGE)
    lock = _load(PACKAGE_LOCK)
    assert package["private"] is True
    assert package["devDependencies"]["newman"] == "6.2.2"
    assert lock["packages"]["node_modules/newman"]["version"] == "6.2.2"
    runner = RUNNER.read_text()
    assert "npm ci --prefix" in runner
    assert "npm install --global" not in runner
