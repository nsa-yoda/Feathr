"""Typed PyMongo Async repository for canonical events."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError, PyMongoError

from event_platform.domain.events import CanonicalEvent, MetadataValue
from event_platform.observability.metrics import MetricsRegistry

_SOURCE_URL_ADAPTER = TypeAdapter(HttpUrl)


class MongoStoreError(RuntimeError):
    """Safe base error for storage failures."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"Mongo operation failed: {operation}")
        self.operation = operation


class EventAlreadyExists(MongoStoreError):
    """The immutable event ID already exists."""


class MongoDependencyError(MongoStoreError):
    """MongoDB or driver failure translated at the storage boundary."""


class InvalidAggregation(ValueError):
    """An application pipeline contains a non-empty mapping stage."""


class EventQuery(BaseModel):
    """Bounded filters and an exclusive timestamp/ID continuation pair."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    event_type: str | None = None
    user_id: str | None = None
    source_url: str | None = None
    timestamp_from: datetime | None = None
    timestamp_to: datetime | None = None
    after_timestamp: datetime | None = None
    after_event_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=1_000)

    @field_validator("event_type", "user_id", "source_url")
    @classmethod
    def bound_query_string(cls, value: str | None, info: ValidationInfo) -> str | None:
        maximum = {"event_type": 128, "user_id": 256, "source_url": 2_048}[str(info.field_name)]
        if value is not None and len(value) > maximum:
            raise ValueError("query filter exceeds its maximum length")
        if value is not None and any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("source_url")
    @classmethod
    def normalize_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = _SOURCE_URL_ADAPTER.validate_python(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("source_url credentials are not allowed")
        return str(parsed)

    @field_validator("timestamp_from", "timestamp_to", "after_timestamp")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("query timestamps must be normalized to UTC")
        return value

    @model_validator(mode="after")
    def require_cursor_pair(self) -> EventQuery:
        if (self.after_timestamp is None) != (self.after_event_id is None):
            raise ValueError("after_timestamp and after_event_id must be supplied together")
        if (
            self.timestamp_from is not None
            and self.timestamp_to is not None
            and self.timestamp_from > self.timestamp_to
        ):
            raise ValueError("timestamp_from must not exceed timestamp_to")
        if (
            self.timestamp_from is not None
            and self.timestamp_to is not None
            and self.timestamp_to - self.timestamp_from > timedelta(days=366)
        ):
            raise ValueError("query date range must not exceed 366 days")
        return self


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False
    expire_after_seconds: int | None = None


REQUIRED_INDEXES: tuple[IndexDefinition, ...] = (
    IndexDefinition("uq_events_event_id", (("event_id", ASCENDING),), unique=True),
    IndexDefinition(
        "ix_events_timestamp_event_id",
        (("timestamp", DESCENDING), ("event_id", DESCENDING)),
    ),
    IndexDefinition(
        "ix_events_event_type_timestamp_event_id",
        (("event_type", ASCENDING), ("timestamp", DESCENDING), ("event_id", DESCENDING)),
    ),
    IndexDefinition(
        "ix_events_user_id_timestamp_event_id",
        (("user_id", ASCENDING), ("timestamp", DESCENDING), ("event_id", DESCENDING)),
    ),
    IndexDefinition(
        "ix_events_source_url_timestamp_event_id",
        (("source_url", ASCENDING), ("timestamp", DESCENDING), ("event_id", DESCENDING)),
    ),
)


def index_models() -> tuple[IndexModel, ...]:
    """Return fresh deterministic models for idempotent bootstrap calls."""

    return tuple(
        IndexModel(
            list(index.keys),
            name=index.name,
            unique=index.unique,
            **(
                {"expireAfterSeconds": index.expire_after_seconds}
                if index.expire_after_seconds is not None
                else {}
            ),
        )
        for index in REQUIRED_INDEXES
    )


def event_to_document(event: CanonicalEvent) -> dict[str, object]:
    """Convert a canonical event to a BSON-safe mapping without driver leakage."""

    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "user_id": event.user_id,
        "source_url": str(event.source_url),
        "metadata": _bson_value(event.metadata),
        "ingested_at": event.ingested_at,
        "schema_version": event.schema_version,
        "payload_hash": event.payload_hash,
        "idempotency_key_hash": event.idempotency_key_hash,
    }


def event_from_document(document: Mapping[str, object]) -> CanonicalEvent:
    """Validate a Mongo document as a canonical event."""

    values = {
        key: _mongo_datetime(value) if key in {"timestamp", "ingested_at"} else value
        for key, value in document.items()
        if key != "_id"
    }
    try:
        return CanonicalEvent.model_validate(values)
    except ValueError:
        raise MongoDependencyError("decode_event") from None


def _mongo_datetime(value: object) -> object:
    """Treat BSON's default naive UTC datetime representation as UTC."""

    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _bson_value(value: MetadataValue) -> object:
    if isinstance(value, dict):
        return {key: _bson_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_bson_value(child) for child in value]
    return value


def _query_filter(query: EventQuery) -> dict[str, object]:
    predicates: list[dict[str, object]] = []
    for field in ("event_type", "user_id", "source_url"):
        value = getattr(query, field)
        if value is not None:
            predicates.append({field: value})
    if query.timestamp_from is not None:
        predicates.append({"timestamp": {"$gte": query.timestamp_from}})
    if query.timestamp_to is not None:
        predicates.append({"timestamp": {"$lte": query.timestamp_to}})
    if query.after_timestamp is not None and query.after_event_id is not None:
        predicates.append(
            {
                "$or": [
                    {"timestamp": {"$lt": query.after_timestamp}},
                    {
                        "timestamp": query.after_timestamp,
                        "event_id": {"$lt": str(query.after_event_id)},
                    },
                ]
            }
        )
    if not predicates:
        return {}
    if len(predicates) == 1:
        return predicates[0]
    return {"$and": predicates}


class MongoEventStore:
    """Own canonical event persistence behind a typed async boundary."""

    def __init__(
        self,
        collection: AsyncCollection[Mapping[str, Any]],
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._collection = collection
        self._metrics = metrics

    async def insert(self, event: CanonicalEvent) -> None:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            await self._collection.insert_one(event_to_document(event))
            outcome = "success"
        except DuplicateKeyError:
            raise EventAlreadyExists("insert_event") from None
        except PyMongoError:
            raise MongoDependencyError("insert_event") from None
        finally:
            self._record_operation("insert", outcome, started_at)

    async def get_by_id(self, event_id: UUID) -> CanonicalEvent | None:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            document = await self._collection.find_one({"event_id": str(event_id)})
            outcome = "success"
        except PyMongoError:
            raise MongoDependencyError("get_event") from None
        finally:
            self._record_operation("get", outcome, started_at)
        return event_from_document(document) if document is not None else None

    async def query(self, query: EventQuery) -> AsyncIterator[CanonicalEvent]:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            cursor = (
                self._collection.find(_query_filter(query))
                .sort([("timestamp", DESCENDING), ("event_id", DESCENDING)])
                .limit(query.limit)
            )
            async for document in cursor:
                yield event_from_document(document)
            outcome = "success"
        except PyMongoError:
            raise MongoDependencyError("query_events") from None
        finally:
            self._record_operation("query", outcome, started_at)

    async def aggregate(
        self,
        pipeline: Sequence[Mapping[str, object]],
        *,
        max_time_ms: int | None = None,
    ) -> list[Mapping[str, object]]:
        stages = _validated_pipeline(pipeline)
        if max_time_ms is not None and max_time_ms <= 0:
            raise InvalidAggregation("aggregation max time must be positive")
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            options = {} if max_time_ms is None else {"maxTimeMS": max_time_ms}
            cursor = await cast(Any, self._collection).aggregate(stages, **options)
            documents = await cursor.to_list(length=None)
            outcome = "success"
        except PyMongoError:
            raise MongoDependencyError("aggregate_events") from None
        finally:
            self._record_operation("aggregate", outcome, started_at)
        return [cast(Mapping[str, object], document) for document in documents]

    async def ensure_indexes(self) -> tuple[str, ...]:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            names = await self._collection.create_indexes(list(index_models()))
            outcome = "success"
        except PyMongoError:
            raise MongoDependencyError("ensure_indexes") from None
        finally:
            self._record_operation("ensure_indexes", outcome, started_at)
        return tuple(names)

    def _record_operation(self, operation: str, outcome: str, started_at: float) -> None:
        if self._metrics is None:
            return
        self._metrics.observe_histogram(
            "event_platform_mongo_operation_latency_seconds",
            max(0.0, time.perf_counter() - started_at),
            {"operation": operation},
        )
        self._metrics.inc(
            "event_platform_mongo_operations_total",
            {"operation": operation, "outcome": outcome},
        )


def _validated_pipeline(
    pipeline: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    if not isinstance(pipeline, Sequence) or isinstance(pipeline, (str, bytes)):
        raise InvalidAggregation("aggregation pipeline must contain mapping stages")
    stages = list(pipeline)
    if any(not isinstance(stage, Mapping) or not stage for stage in stages):
        raise InvalidAggregation("aggregation stages must be non-empty mappings")
    return stages
