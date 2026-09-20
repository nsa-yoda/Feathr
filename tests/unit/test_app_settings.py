"""Settings are validated during app lifespan before serving requests."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from event_platform.main import create_app


@pytest.mark.unit
def test_app_owns_injected_settings() -> None:
    from event_platform.core.settings import ServiceSettings

    settings = ServiceSettings(env="test", log_level="WARNING")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert app.state.settings is settings


@pytest.mark.unit
def test_invalid_environment_prevents_app_startup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from event_platform.core.settings import SettingsStartupError

    monkeypatch.setenv("EVENT_PLATFORM_LOG_LEVEL", "LOUD")

    with pytest.raises(SettingsStartupError):
        with TestClient(create_app()) as client:
            client.get("/health/live")

    startup_failures = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "service.startup_failed"
    ]
    assert startup_failures
    assert startup_failures[-1].error_fields == ["EVENT_PLATFORM_LOG_LEVEL"]


@pytest.mark.unit
def test_base_app_needs_no_external_dependency_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)

    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "alive"}


@pytest.mark.unit
def test_production_requires_canonical_mongo() -> None:
    from event_platform.core.settings import ServiceSettings

    with pytest.raises(ValidationError) as error:
        ServiceSettings(env="production", mongo_url=None)

    assert "mongo_url is required in production" in str(error.value)


@pytest.mark.unit
def test_loaded_production_configuration_names_missing_mongo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    from pathlib import Path

    from event_platform.core.settings import SettingsStartupError, load_settings

    monkeypatch.chdir(Path(str(tmp_path)))
    monkeypatch.setenv("EVENT_PLATFORM_ENV", "production")
    monkeypatch.delenv("EVENT_PLATFORM_MONGO_URL", raising=False)

    with pytest.raises(SettingsStartupError) as error:
        load_settings()

    assert error.value.fields == ("EVENT_PLATFORM_MONGO_URL",)
