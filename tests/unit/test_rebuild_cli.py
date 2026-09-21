"""CLI command paths are part of the release and operational contract."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from event_platform.core.settings import ServiceSettings, SettingsStartupError
from event_platform.search import rebuild as module
from event_platform.search.rebuild import RebuildPhase, RebuildRecord


def _record() -> RebuildRecord:
    now = datetime.now(UTC)
    return RebuildRecord(
        rebuild_id=uuid4(),
        phase=RebuildPhase.COMPLETED,
        started_at=now,
        completed_at=now,
        source_collection="events",
        target_index="events-v2",
        owner="cli",
        lease_expires_at=now + timedelta(minutes=1),
    )


@pytest.mark.unit
def test_cli_parser_and_confirmation_guard(capsys: pytest.CaptureFixture[str]) -> None:
    assert module.main([]) == 0
    assert "refusing" in str(_raises_system_exit(lambda: module.main(["run"])))
    assert "usage:" in capsys.readouterr().out


@pytest.mark.unit
def test_run_command_classifies_configuration_and_rebuild_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "load_settings", lambda: _settings_error())
    assert module.main(["run", "--confirm"]) == 2
    monkeypatch.setattr(module, "load_settings", lambda: ServiceSettings(env="test"))
    assert module.main(["run", "--confirm"]) == 2

    async def fail_run() -> object:
        raise module.RebuildError("bulk_failed")

    @asynccontextmanager
    async def runtime(_settings: ServiceSettings):
        yield type("Rebuilder", (), {"run": fail_run})()

    monkeypatch.setattr("event_platform.search.rebuild_runtime.configured_rebuild_runtime", runtime)
    monkeypatch.setattr(
        module,
        "load_settings",
        lambda: ServiceSettings(
            env="test", mongo_url="mongodb://mongo", elasticsearch_url="http://es"
        ),
    )
    assert module.main(["run", "--confirm"]) == 1


@pytest.mark.unit
def test_run_command_prints_success_and_status_handles_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()

    async def succeed() -> RebuildRecord:
        return record

    @asynccontextmanager
    async def runtime(_settings: ServiceSettings):
        yield SimpleNamespace(run=succeed)

    monkeypatch.setattr("event_platform.search.rebuild_runtime.configured_rebuild_runtime", runtime)
    monkeypatch.setattr(
        module,
        "load_settings",
        lambda: ServiceSettings(
            env="test", mongo_url="mongodb://mongo", elasticsearch_url="http://es"
        ),
    )
    assert module.main(["run", "--confirm"]) == 0

    monkeypatch.setattr(module, "load_settings", lambda: ServiceSettings(env="test"))
    assert module.main(["status"]) == 0
    monkeypatch.setattr(module, "load_settings", lambda: _settings_error())
    assert module.main(["status"]) == 2
    monkeypatch.setattr(
        module, "load_settings", lambda: ServiceSettings(env="test", mongo_url="mongodb://mongo")
    )
    assert module.main(["status", "--rebuild-id", "invalid"]) == 2


def _settings_error() -> ServiceSettings:
    raise SettingsStartupError("invalid", fields=("EVENT_PLATFORM_MONGO_URL",))


def _raises_system_exit(function: object) -> BaseException:
    try:
        function()  # type: ignore[operator]
    except BaseException as error:
        return error
    raise AssertionError("expected SystemExit")
