"""Typed settings and redacted startup diagnostics."""

import pytest
from pydantic import ValidationError


@pytest.mark.unit
def test_settings_use_safe_foundation_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from event_platform.core.settings import ServiceSettings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)

    settings = ServiceSettings()
    assert settings.env == "local"
    assert settings.log_level == "INFO"


@pytest.mark.unit
def test_settings_accept_documented_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from event_platform.core.settings import ServiceSettings

    monkeypatch.setenv("EVENT_PLATFORM_ENV", "production")
    monkeypatch.setenv("EVENT_PLATFORM_LOG_LEVEL", "WARNING")

    settings = ServiceSettings()
    assert settings.env == "production"
    assert settings.log_level == "WARNING"


@pytest.mark.unit
def test_settings_reject_unsupported_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from event_platform.core.settings import ServiceSettings

    monkeypatch.setenv("EVENT_PLATFORM_ENV", "unknown")
    with pytest.raises(ValidationError):
        ServiceSettings()

    monkeypatch.delenv("EVENT_PLATFORM_ENV")
    monkeypatch.setenv("EVENT_PLATFORM_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        ServiceSettings()


@pytest.mark.unit
def test_startup_diagnostic_names_field_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from event_platform.core.settings import SettingsStartupError, load_settings

    invalid_value = "SENTINEL_UNSAFE_VALUE"
    monkeypatch.setenv("EVENT_PLATFORM_LOG_LEVEL", invalid_value)

    with pytest.raises(SettingsStartupError) as error:
        load_settings()

    assert "EVENT_PLATFORM_LOG_LEVEL" in str(error.value)
    assert invalid_value not in str(error.value)
