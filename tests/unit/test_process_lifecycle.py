"""Exercise the documented process-level start and stop path."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.unit


def _listening_socket() -> socket.socket:
    """Reserve a listening socket so the child cannot lose a port race."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    return sock


def _wait_for_liveness(process: subprocess.Popen[str], url: str) -> tuple[int, bytes]:
    deadline = time.monotonic() + 10
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise AssertionError(f"uvicorn exited before liveness: {output}")
        try:
            with urlopen(url, timeout=0.5) as response:
                return response.status, response.read()
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"liveness did not become available: {last_error}")


def test_uvicorn_factory_process_starts_serves_and_stops_cleanly() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    listener = _listening_socket()
    port = int(listener.getsockname()[1])
    environment = os.environ.copy()
    source_path = str(repo_root / "src")
    log_config = repo_root / "src/event_platform/core/uvicorn_logging.json"
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_path, environment.get("PYTHONPATH")) if value
    )
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "event_platform.main:create_app",
                "--factory",
                "--fd",
                str(listener.fileno()),
                "--log-config",
                str(log_config),
                "--workers",
                "1",
            ],
            cwd=repo_root,
            env=environment,
            pass_fds=(listener.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        listener.close()

    try:
        status, body = _wait_for_liveness(
            process,
            f"http://127.0.0.1:{port}/health/live?token=SENTINEL_SECRET",
        )
        assert status == 200
        assert json.loads(body) == {"status": "alive"}

        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=10) == 0, process.stdout.read() if process.stdout else ""
        output = process.stdout.read() if process.stdout else ""
        records = [json.loads(line) for line in output.splitlines() if line.strip()]
        assert records
        assert all(record["service"] == "event_platform" for record in records)
        assert all(record["event"] for record in records)
        assert any(record.get("event") == "service.startup" for record in records)
        assert any(record.get("event") == "service.shutdown" for record in records)
        assert "SENTINEL_SECRET" not in output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
