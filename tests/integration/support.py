"""Shared real-service integration harness primitives."""

from __future__ import annotations

import asyncio
import math
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from redis.asyncio import Redis
from redis.exceptions import RedisError


@dataclass(frozen=True, slots=True)
class IntegrationNamespace:
    """Unique resource names owned by one integration lifecycle."""

    suffix: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{12}", self.suffix):
            raise ValueError("integration namespace suffix must be 12 lowercase hex characters")

    @property
    def database(self) -> str:
        return f"event_platform_it_{self.suffix}"

    @property
    def collection(self) -> str:
        return "events"

    @property
    def checkpoint_collection(self) -> str:
        return "projection_checkpoints"

    @property
    def rebuild_collection(self) -> str:
        return "rebuilds"

    @property
    def lock_collection(self) -> str:
        return "rebuild_locks"

    @property
    def alias(self) -> str:
        return f"events-it-{self.suffix}"

    @property
    def target_index(self) -> str:
        return f"events-it-target-{self.suffix}"

    @property
    def redis_prefix(self) -> str:
        return f"event-platform-it:{self.suffix}:"


class PollTimeout(TimeoutError):
    """A bounded integration poll did not observe its expected state."""


def new_namespace() -> IntegrationNamespace:
    return IntegrationNamespace(uuid4().hex[:12])


def require_env(*names: str) -> dict[str, str]:
    values = {name: os.getenv(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip(f"integration endpoints not configured: {', '.join(missing)}")
    return {name: value for name, value in values.items() if value is not None}


async def require_mongo(uri: str, *, require_replica_set: bool = False) -> None:
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=2_000, connectTimeoutMS=2_000)
    try:
        await client.admin.command("ping")
        if require_replica_set:
            hello = await client.admin.command("hello")
            if not isinstance(hello.get("setName"), str) or not hello["setName"]:
                pytest.skip("MONGO_URI MongoDB replica set is required for change streams")
    except (ConnectionError, OSError, PyMongoError) as error:
        pytest.skip(f"MONGO_URI MongoDB unavailable: {type(error).__name__}")
    finally:
        await client.close()


async def require_elasticsearch(url: str) -> None:
    client = AsyncElasticsearch(hosts=[url], request_timeout=2)
    try:
        await client.info()
    except (ConnectionError, OSError, RuntimeError, TransportError) as error:
        pytest.skip(f"ELASTICSEARCH_URL Elasticsearch unavailable: {type(error).__name__}")
    finally:
        await client.close()


async def require_redis(url: str) -> None:
    client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
    except (ConnectionError, OSError, RedisError) as error:
        pytest.skip(f"REDIS_URL Redis unavailable: {type(error).__name__}")
    finally:
        await client.aclose()


def safe_observation(value: object) -> str:
    """Bound poll diagnostics without exposing payloads or dependency details."""

    if value is None:
        return "none"
    if isinstance(value, Mapping):
        fields: list[str] = []
        for key in sorted(value, key=str)[:8]:
            child = value[key]
            safe_key = re.sub(r"[^A-Za-z0-9_.-]", "?", str(key))[:32]
            fields.append(f"{safe_key}={_safe_scalar(child)}")
        return f"mapping({', '.join(fields)})"
    return _safe_scalar(value)


def _safe_scalar(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)[:32]
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)[:32]
    if isinstance(value, str) and value in {"absent", "not-ready", "ready", "unavailable"}:
        return value
    return type(value).__name__


async def poll_until[T](
    operation: str,
    check: Callable[[], Awaitable[T | None]],
    *,
    timeout_seconds: float = 15.0,
    interval_seconds: float = 0.1,
    observe: Callable[[T | None], object] | None = None,
) -> T:
    """Poll with a monotonic deadline and a safe timeout diagnostic.

    ``observe`` may return a small status summary for a failed attempt. The
    summary is sanitized before it is included in a timeout error.
    """

    if (
        not operation
        or len(operation) > 160
        or not re.fullmatch(r"[A-Za-z0-9 _:/=-]+", operation)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or not math.isfinite(interval_seconds)
        or not 0 < interval_seconds <= 5
    ):
        raise ValueError("poll arguments are invalid")
    deadline = monotonic() + timeout_seconds
    attempts = 0
    last_observation: object = None
    while True:
        attempts += 1
        result = await check()
        if result is not None:
            return result
        last_observation = observe(result) if observe is not None else {"state": "not-ready"}
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PollTimeout(
                f"{operation} timed out after {attempts} attempts; "
                f"last_observation={safe_observation(last_observation)}"
            )
        await asyncio.sleep(min(interval_seconds, remaining))
