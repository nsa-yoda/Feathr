"""Validated runtime settings for the foundation service."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv.parser import parse_stream
from pydantic import Field, ValidationError, ValidationInfo, field_validator
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
    queue_capacity: int = Field(default=1_000, ge=1, le=100_000)
    queue_visibility_timeout: float = Field(default=30.0, ge=0.0, le=86_400.0)
    queue_send_timeout: float = Field(default=1.0, ge=0.0, le=60.0)
    idempotency_replay_window_seconds: int = Field(default=86_400, ge=60, le=2_592_000)
    request_body_max_bytes: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    request_query_max_bytes: int = Field(default=8_192, ge=256, le=65_536)
    dependency_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    cors_allowed_origin: str | None = Field(default=None, max_length=2_048)
    shutdown_grace_period: float = Field(default=5.0, ge=0.0, le=300.0)
    worker_concurrency: int = Field(default=1, ge=1, le=100)
    mongo_url: str | None = Field(default=None, max_length=2_048)
    mongo_database: str = Field(default="event_platform", min_length=1, max_length=128)
    mongo_collection: str = Field(default="events", min_length=1, max_length=128)
    elasticsearch_url: str | None = Field(default=None, max_length=2_048)
    elasticsearch_alias: str = Field(default="events-search", min_length=1, max_length=255)
    cursor_signing_key: str | None = Field(default=None, min_length=16, max_length=128)
    cursor_previous_signing_key: str | None = Field(default=None, min_length=16, max_length=128)
    production_api_token: str | None = Field(default=None, min_length=32, max_length=256)
    redis_url: str | None = Field(default=None, max_length=2_048)
    realtime_cache_ttl_seconds: int = Field(default=10, ge=1, le=300)
    realtime_default_window_minutes: int = Field(default=5, ge=1, le=60)
    realtime_max_event_types: int = Field(default=1_000, ge=1, le=1_000)
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0, le=10)
    rate_limit_local_max_entries: int = Field(default=1_024, ge=1, le=100_000)
    rate_limit_ingestion_capacity: int = Field(default=1_000, ge=1, le=100_000)
    rate_limit_ingestion_refill: float = Field(default=100.0, ge=0.001, le=100_000.0)
    rate_limit_ingestion_cost: int = Field(default=1, ge=1, le=100_000)
    rate_limit_normal_capacity: int = Field(default=120, ge=1, le=100_000)
    rate_limit_normal_refill: float = Field(default=20.0, ge=0.001, le=100_000.0)
    rate_limit_normal_cost: int = Field(default=1, ge=1, le=100_000)
    rate_limit_expensive_capacity: int = Field(default=30, ge=1, le=100_000)
    rate_limit_expensive_refill: float = Field(default=5.0, ge=0.001, le=100_000.0)
    rate_limit_expensive_cost: int = Field(default=1, ge=1, le=100_000)
    rate_limit_ops_capacity: int = Field(default=20, ge=1, le=100_000)
    rate_limit_ops_refill: float = Field(default=2.0, ge=0.001, le=100_000.0)
    rate_limit_ops_cost: int = Field(default=1, ge=1, le=100_000)

    @field_validator(
        "rate_limit_ingestion_cost",
        "rate_limit_normal_cost",
        "rate_limit_expensive_cost",
        "rate_limit_ops_cost",
    )
    @classmethod
    def validate_rate_limit_cost(cls, value: int, info: ValidationInfo) -> int:
        capacity_name = str(info.field_name).replace("_cost", "_capacity")
        capacity = info.data.get(capacity_name)
        if isinstance(capacity, int) and value > capacity:
            raise ValueError(f"{info.field_name} cannot exceed {capacity_name}")
        return value

    @field_validator("queue_visibility_timeout")
    @classmethod
    def validate_visibility_timeout(cls, value: float, info: ValidationInfo) -> float:
        if info.data.get("env") == "production" and value <= 0:
            raise ValueError("queue_visibility_timeout must be positive in production")
        return value

    @field_validator("cursor_signing_key")
    @classmethod
    def validate_cursor_key(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("env") == "production" and not value:
            raise ValueError("cursor_signing_key is required in production")
        return value

    @field_validator("production_api_token")
    @classmethod
    def validate_production_token(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("env") == "production" and not value:
            raise ValueError("production_api_token is required in production")
        if value is not None and value.lower() in {"changeme", "password", "development-token"}:
            raise ValueError("production_api_token must not be a placeholder")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"redis", "rediss", "unix"}:
            raise ValueError("redis_url must use redis, rediss, or unix scheme")
        if parsed.scheme == "unix" and not parsed.path:
            raise ValueError("unix redis_url must include a socket path")
        if parsed.scheme != "unix" and not parsed.netloc:
            raise ValueError("redis_url must include a host")
        return value

    @field_validator("mongo_url")
    @classmethod
    def validate_mongo_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("env") == "production" and value is None:
            raise ValueError("mongo_url is required in production")
        if value is not None:
            parsed = urlparse(value)
            if parsed.scheme not in {"mongodb", "mongodb+srv"}:
                raise ValueError("mongo_url must use mongodb or mongodb+srv scheme")
            if not parsed.netloc:
                raise ValueError("mongo_url must include a host")
        return value

    @field_validator("elasticsearch_url")
    @classmethod
    def validate_elasticsearch_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("elasticsearch_url must use http or https scheme")
            if not parsed.netloc:
                raise ValueError("elasticsearch_url must include a host")
        return value

    @field_validator("cors_allowed_origin")
    @classmethod
    def validate_cors_allowed_origin(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.netloc == "*"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("cors_allowed_origin must be one exact HTTP(S) origin")
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65_535:
                raise ValueError
        except ValueError:
            raise ValueError("cors_allowed_origin must use a valid port") from None
        if parsed.path == "/":
            raise ValueError("cors_allowed_origin must not include a path")
        return f"{parsed.scheme}://{parsed.netloc}"


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
