"""Importing foundation modules must not start network work or background tasks."""

import subprocess
import sys

import pytest


@pytest.mark.unit
def test_imports_have_no_network_or_background_side_effects() -> None:
    script = """
import asyncio
import importlib
import pkgutil
import socket

def forbidden(*args, **kwargs):
    raise AssertionError("network or background work started during import")

socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
asyncio.create_task = forbidden
asyncio.ensure_future = forbidden

import event_platform
for module in pkgutil.walk_packages(event_platform.__path__, event_platform.__name__ + "."):
    importlib.import_module(module.name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
