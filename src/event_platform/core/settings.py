"""Validated runtime settings for the foundation service."""

from pathlib import Path
from typing import Literal

from dotenv.parser import parse_stream
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVENT_PLATFORM_",
        env_file=".env",
        hide_input_in_errors=True,
        extra="forbid",
    )

    env: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class SettingsStartupError(RuntimeError):
    """The service cannot safely start with its configured values."""

    def __init__(self, message: str, *, fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.fields = fields


def load_settings() -> ServiceSettings:
    try:
        _validate_dotenv_source(Path(".env"))
        return ServiceSettings()
    except SettingsStartupError:
        raise
    except ValidationError as error:
        fields = sorted(
            {
                _setting_name(str(issue["loc"][0]))
                for issue in error.errors(include_input=False)
                if issue["loc"]
            }
        )
        names = ", ".join(fields) if fields else "unknown setting"
        raise SettingsStartupError(
            f"Invalid configuration: {names}", fields=tuple(fields)
        ) from None
    except (SettingsError, OSError, UnicodeError):
        raise SettingsStartupError(
            "Configuration source could not be loaded.",
            fields=("configuration_source",),
        ) from None


def _setting_name(name: str) -> str:
    environment_name = name.upper()
    if environment_name.startswith("EVENT_PLATFORM_"):
        return environment_name
    return f"EVENT_PLATFORM_{environment_name}"


def _validate_dotenv_source(path: Path) -> None:
    if not path.is_file():
        return
    try:
        with path.open(encoding="utf-8") as stream:
            if any(binding.error for binding in parse_stream(stream)):
                raise SettingsStartupError(
                    "Configuration source could not be loaded.",
                    fields=("configuration_source",),
                )
    except (OSError, UnicodeError):
        raise SettingsStartupError(
            "Configuration source could not be loaded.",
            fields=("configuration_source",),
        ) from None
