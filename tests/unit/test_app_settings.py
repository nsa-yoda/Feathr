"""Settings are validated during app lifespan before serving requests."""

import pytest
from fastapi.testclient import TestClient

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
def test_invalid_environment_prevents_app_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    from event_platform.core.settings import SettingsStartupError

    monkeypatch.setenv("EVENT_PLATFORM_LOG_LEVEL", "LOUD")

    with pytest.raises(SettingsStartupError):
        with TestClient(create_app()) as client:
            client.get("/health/live")


@pytest.mark.unit
def test_base_app_needs_no_external_dependency_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)

    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
