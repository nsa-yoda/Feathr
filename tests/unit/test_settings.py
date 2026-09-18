"""Typed settings and redacted startup diagnostics."""

from pathlib import Path

import pytest
from pydantic import ValidationError


@pytest.mark.unit
def test_settings_use_safe_foundation_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from event_platform.core.settings import ServiceSettings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)
    monkeypatch.chdir(tmp_path)

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
def test_settings_load_documented_dotenv_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from event_platform.core.settings import ServiceSettings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)
    working_directory = tmp_path / "dotenv"
    working_directory.mkdir()
    (working_directory / ".env").write_text("EVENT_PLATFORM_LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.chdir(working_directory)

    settings = ServiceSettings()

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


@pytest.mark.unit
def test_startup_diagnostic_normalizes_extra_environment_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from event_platform.core.settings import SettingsStartupError, load_settings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)
    working_directory = tmp_path / "extra"
    working_directory.mkdir()
    (working_directory / ".env").write_text(
        "EVENT_PLATFORM_SECRET=SENTINEL_UNSAFE_VALUE\n", encoding="utf-8"
    )
    monkeypatch.chdir(working_directory)

    with pytest.raises(SettingsStartupError) as error:
        load_settings()

    assert error.value.fields == ("EVENT_PLATFORM_SECRET",)
    assert "EVENT_PLATFORM_EVENT_PLATFORM_SECRET" not in str(error.value)
    assert "SENTINEL_UNSAFE_VALUE" not in str(error.value)


@pytest.mark.unit
def test_startup_diagnostic_classifies_unreadable_configuration_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from event_platform.core.settings import SettingsStartupError, load_settings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)
    working_directory = tmp_path / "invalid-encoding"
    working_directory.mkdir()
    (working_directory / ".env").write_bytes(b"EVENT_PLATFORM_LOG_LEVEL=\xff\n")
    monkeypatch.chdir(working_directory)

    with pytest.raises(SettingsStartupError) as error:
        load_settings()

    assert error.value.fields == ("configuration_source",)
    assert "ff" not in str(error.value)


@pytest.mark.unit
def test_startup_diagnostic_rejects_malformed_configuration_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from event_platform.core.settings import SettingsStartupError, load_settings

    monkeypatch.delenv("EVENT_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("EVENT_PLATFORM_LOG_LEVEL", raising=False)
    working_directory = tmp_path / "malformed"
    working_directory.mkdir()
    (working_directory / ".env").write_text("EVENT_PLATFORM_LOG_LEVEL WARNING\n", encoding="utf-8")
    monkeypatch.chdir(working_directory)

    with pytest.raises(SettingsStartupError) as error:
        load_settings()

    assert error.value.fields == ("configuration_source",)
