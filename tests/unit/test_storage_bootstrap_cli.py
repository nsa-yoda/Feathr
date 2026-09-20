"""Operator CLI contract for versioned storage bootstrap."""

from __future__ import annotations

import logging

import pytest

from event_platform import cli
from event_platform.core.settings import ServiceSettings
from event_platform.storage.bootstrap import StorageSchemaError, StorageVerification

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("command", ["bootstrap", "verify"])
def test_storage_commands_dispatch_to_storage_boundary(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "storage_main", lambda operation: calls.append(operation) or 0)

    assert cli.main(["storage", command]) == 0
    assert calls == [command]


def test_storage_parser_rejects_unknown_operation() -> None:
    with pytest.raises(SystemExit):
        cli.main(["storage", "drop"])


class _FakeClient:
    def __init__(self) -> None:
        self.database = object()
        self.closed = False

    def __getitem__(self, name: str) -> object:
        del name
        return self.database

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_storage_operation_closes_client_and_logs_safe_result(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient()
    settings = ServiceSettings(env="test", mongo_url="mongodb://user:secret@mongo.test:27017")

    async def bootstrap(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        return StorageVerification(1, "a" * 64, 10)

    monkeypatch.setattr(cli, "AsyncMongoClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(cli, "bootstrap_storage", bootstrap)

    with caplog.at_level(logging.INFO):
        assert await cli._run_storage_operation("bootstrap", settings) == 0

    assert client.closed is True
    complete = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "storage.operation_complete"
    ]
    assert complete[-1].schema_version == 1
    assert complete[-1].verified_indexes == 10
    assert "secret" not in complete[-1].getMessage()


@pytest.mark.asyncio
async def test_storage_operation_returns_failure_without_raw_driver_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient()
    settings = ServiceSettings(env="test", mongo_url="mongodb://user:secret@mongo.test:27017")

    async def fail(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        raise StorageSchemaError("index_missing", collection="events", index="required")

    monkeypatch.setattr(cli, "AsyncMongoClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(cli, "verify_storage", fail)

    with caplog.at_level(logging.ERROR):
        assert await cli._run_storage_operation("verify", settings) == 1

    assert client.closed is True
    failure = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "storage.operation_failed"
    ][-1]
    assert failure.classification == "index_missing"
    assert "secret" not in failure.getMessage()


def test_storage_command_requires_mongo_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: ServiceSettings(env="test"))
    assert cli.storage_main("verify") == 2
