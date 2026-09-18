"""Exercise the documented process-level start and stop path."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.unit


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
        except (OSError, URLError) as error:
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"liveness did not become available: {last_error}")


def test_uvicorn_factory_process_starts_serves_and_stops_cleanly() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    port = _free_port()
    environment = os.environ.copy()
    source_path = str(repo_root / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_path, environment.get("PYTHONPATH")) if value
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "event_platform.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
        ],
        cwd=repo_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        status, body = _wait_for_liveness(process, f"http://127.0.0.1:{port}/health/live")
        assert status == 200
        assert json.loads(body) == {"status": "alive"}

        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=10) == 0, process.stdout.read() if process.stdout else ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
