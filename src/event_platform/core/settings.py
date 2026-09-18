"""Validated runtime settings for the foundation service."""

from typing import Literal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVENT_PLATFORM_",
        hide_input_in_errors=True,
        extra="forbid",
    )

    env: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class SettingsStartupError(RuntimeError):
    """The service cannot safely start with its configured values."""


def load_settings() -> ServiceSettings:
    try:
        return ServiceSettings()
    except ValidationError as error:
        fields = sorted(
            {
                f"EVENT_PLATFORM_{str(issue['loc'][0]).upper()}"
                for issue in error.errors(include_input=False)
                if issue["loc"]
            }
        )
        names = ", ".join(fields) if fields else "unknown setting"
        raise SettingsStartupError(f"Invalid configuration: {names}") from None
