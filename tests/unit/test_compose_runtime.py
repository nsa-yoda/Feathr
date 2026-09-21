"""Docker-free regression checks for the reviewer Compose runtime contract."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "docker-compose.yml"
SMOKE = ROOT / "scripts/smoke"


def _service_block(text: str, service: str) -> str:
    match = re.search(
        rf"^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, service
    return match.group(0)


def test_compose_defines_required_services_and_health_conditions() -> None:
    text = COMPOSE.read_text()
    for service in (
        "app:",
        "mongo:",
        "mongo-init:",
        "storage-bootstrap:",
        "elasticsearch:",
        "redis:",
        "ui:",
    ):
        assert f"  {service}" in text
    app = _service_block(text, "app")
    storage_bootstrap = _service_block(text, "storage-bootstrap")
    ui = _service_block(text, "ui")
    assert "storage-bootstrap:\n        condition: service_completed_successfully" in app
    assert "mongo-init:\n        condition: service_completed_successfully" in storage_bootstrap
    assert '"storage", "bootstrap"' in storage_bootstrap
    assert "elasticsearch:\n        condition: service_healthy" in app
    assert "redis:\n        condition: service_healthy" in app
    assert "app:\n        condition: service_healthy" in ui
    for service in ("app", "mongo", "elasticsearch", "redis", "ui"):
        assert "healthcheck:" in _service_block(text, service)


def test_compose_defines_named_state_volumes_and_network() -> None:
    text = COMPOSE.read_text()
    for volume in ("mongo_data:", "mongo_config:", "elasticsearch_data:", "redis_data:"):
        assert volume in text
    assert "feathr:" in text
    assert "driver: bridge" in text


def test_compose_uses_replica_set_and_single_uvicorn_worker() -> None:
    compose = COMPOSE.read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "--replSet" in compose
    assert "replicaSet=rs0" in compose
    assert '"--workers", "1"' in dockerfile
    assert "pip install --no-cache-dir uv==0.12.17" in dockerfile


def test_compose_runtime_defaults_and_resources_are_explicit() -> None:
    compose = COMPOSE.read_text()
    env = (ROOT / ".env.example").read_text()
    app = _service_block(compose, "app")
    assert '"${APP_PORT:-8000}:8000"' in compose
    assert '"${UI_PORT:-3000}:8080"' in compose
    assert "EVENT_PLATFORM_MONGO_URL" in app
    assert (
        "EVENT_PLATFORM_ELASTICSEARCH_URL: ${EVENT_PLATFORM_ELASTICSEARCH_URL:-http://elasticsearch:9200}"
        in app
    )
    assert (
        "EVENT_PLATFORM_ELASTICSEARCH_ALIAS: ${EVENT_PLATFORM_ELASTICSEARCH_ALIAS:-events-search}"
        in app
    )
    assert "EVENT_PLATFORM_REDIS_URL: ${EVENT_PLATFORM_REDIS_URL:-redis://redis:6379/0}" in app
    assert "mem_limit:" in app and "cpus:" in app
    assert "EVENT_PLATFORM_MONGO_URL=mongodb://mongo:27017/?replicaSet=rs0" in env
    assert "EVENT_PLATFORM_ELASTICSEARCH_URL=http://elasticsearch:9200" in env
    assert "EVENT_PLATFORM_ELASTICSEARCH_ALIAS=events-search" in env
    assert "EVENT_PLATFORM_REDIS_URL=redis://redis:6379/0" in env
    assert "REDIS_PASSWORD=" in env
    assert "docker compose down -v" in (ROOT / "README.md").read_text()
    assert "mongo:8.3.11" in compose
    assert "elasticsearch/elasticsearch:9.5.4" in compose
    assert "redis:8.10.1-alpine" in compose


def test_final_images_are_non_root_and_ui_proxies_api() -> None:
    assert "USER 10001:10001" in (ROOT / "Dockerfile").read_text()
    assert "USER 101" in (ROOT / "frontend/Dockerfile").read_text()
    assert "proxy_pass http://app:8000/" in (ROOT / "frontend/nginx.conf").read_text()


def test_smoke_is_bounded_and_checks_all_acceptance_surfaces() -> None:
    text = SMOKE.read_text()
    assert "SMOKE_DEADLINE_SECONDS" in text
    for endpoint in (
        "health/live",
        "health/ready",
        "events",
        "events/search",
        "events/stats/realtime",
    ):
        assert endpoint in text
    assert "docker compose" in text
    assert "Idempotency-Key" in text
    assert "!= 202" in text
    assert ".items | any" in text
    assert '"smoke.event"' in text
    assert "compose_pid=$!" in text
    assert "curl_with_deadline" in text
    assert "--connect-timeout" in text
    assert "--max-time" in text
    assert "exit 1" in text


def test_mongo_init_is_idempotent_and_bounded_without_docker(tmp_path: Path) -> None:
    init_script = (ROOT / "docker/mongo-init.sh").read_text()
    assert "serverSelectionTimeoutMS=1000" in init_script
    assert "connectTimeoutMS=1000" in init_script
    assert "socketTimeoutMS=1000" in init_script
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "mongosh.log"
    (bin_dir / "mongosh").write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" >> "$MONGO_LOG"\n'
        'if [[ "$*" == *db.adminCommand* ]]; then [[ "$MODE" != ping-fails ]] && echo 1\n'
        'elif [[ "$*" == *"rs.status().ok"* ]]; then [[ "$MODE" == ready ]] && echo 1\n'
        'elif [[ "$*" == *"rs.status().myState"* ]]; then [[ "$MODE" == init-ready-timeout ]] && echo 2 || [[ "$MODE" != ping-fails ]] && echo 1\n'  # noqa: E501
        'elif [[ "$*" == *rs.initiate* ]]; then [[ "$MODE" == init-fails ]] && exit 7 || echo 1\n'
        "fi\n"
    )
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
    for command in (bin_dir / "mongosh", bin_dir / "sleep"):
        command.chmod(0o755)

    def run(mode: str, deadline: str = "2") -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "MONGO_LOG": str(log),
            "MODE": mode,
            "MONGO_INIT_URI": "mongodb://mongo/?directConnection=true",
            "MONGO_REPLICA_URI": "mongodb://mongo/?replicaSet=rs0",
            "MONGO_INIT_DEADLINE_SECONDS": deadline,
        }
        return subprocess.run(
            ["bash", str(ROOT / "docker/mongo-init.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    first = run("init")
    assert first.returncode == 0
    assert "rs.initiate" in log.read_text()
    log.write_text("")
    already_ready = run("ready")
    assert already_ready.returncode == 0
    assert "rs.initiate" not in log.read_text()
    assert run("ping-fails").returncode != 0
    assert run("init-ready-timeout").returncode != 0
    assert run("init-fails").returncode != 0
    assert run("init", "invalid").returncode != 0


def test_smoke_success_and_unavailable_api_paths_are_executable_without_docker(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    (bin_dir / "docker").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bin_dir / "jq").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == -cn ]]; then echo "{}"; elif [[ "$1" == -er ]]; then echo event-1; fi\n'
    )
    (bin_dir / "curl").write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$CURL_LOG"\n'
        'out=""; url=""; method=GET\n'
        'while (($#)); do case "$1" in -o) out=$2; shift 2;; -X) method=$2; shift 2;; -w) shift 2;; -*) shift;; *) url=$1; shift;; esac; done\n'  # noqa: E501
        'if [[ "$SMOKE_MODE" == fail && "$url" == */health/live ]]; then printf "{}" > "$out"; echo 503; exit 0; fi\n'  # noqa: E501
        'if [[ "$method" == POST ]]; then printf "{\\"event_id\\":\\"event-1\\"}" > "$out"; echo 202\n'  # noqa: E501
        'elif [[ "$url" == */events/search* ]]; then printf "{\\"items\\":[{\\"event_id\\":\\"event-1\\"}]}" > "$out"; echo 200\n'  # noqa: E501
        'elif [[ "$url" == */events?* ]]; then printf "{\\"items\\":[{\\"event_id\\":\\"event-1\\"}]}" > "$out"; echo 200\n'  # noqa: E501
        'elif [[ "$url" == */events/stats/realtime* ]]; then printf "{\\"by_event_type\\":{\\"smoke.event\\":1}}" > "$out"; echo 200\n'  # noqa: E501
        'else printf "{\\"status\\":\\"alive\\"}" > "$out"; echo 200; fi\n'
    )
    for command in bin_dir.iterdir():
        command.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CURL_LOG": str(curl_log),
        "SMOKE_DEADLINE_SECONDS": "5",
        "COMPOSE_PROJECT_NAME": "feathr-test",
        "APP_PORT": "8000",
        "SMOKE_MODE": "success",
    }
    success = subprocess.run(
        ["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=8, check=False
    )
    assert success.returncode == 0, success.stderr
    assert "smoke passed for event event-1" in success.stdout
    curl_requests = curl_log.read_text()
    assert "Idempotency-Key: smoke-" in curl_requests
    assert "/events/search?q=compose-smoke&event_type=smoke.event&limit=50" in curl_requests

    env["SMOKE_MODE"] = "fail"
    failure = subprocess.run(
        ["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=8, check=False
    )
    assert failure.returncode != 0
