"""Pure event input validation and canonical event construction."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

type MetadataValue = (
    dict[str, MetadataValue] | list[MetadataValue] | str | int | float | bool | None
)
type MetadataObject = dict[str, MetadataValue]

MAX_EVENT_TYPE_LENGTH = 128
MAX_USER_ID_LENGTH = 256
MAX_SOURCE_URL_LENGTH = 2_048
MAX_METADATA_BYTES = 16 * 1024
MAX_METADATA_DEPTH = 5
MAX_METADATA_KEYS = 64
MAX_METADATA_KEY_LENGTH = 64
MAX_METADATA_STRING_LENGTH = 512
MAX_METADATA_LIST_LENGTH = 128
MAX_METADATA_NUMBER_ABS = 10**18
MAX_FUTURE_SKEW = timedelta(minutes=5)
_SERVER_OWNED_FIELDS = {
    "event_id",
    "ingested_at",
    "schema_version",
    "payload_hash",
    "idempotency_key_hash",
    "idempotency_key",
}


class MetadataContractError(ValueError):
    """A metadata value violates a bounded domain contract category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _walk_metadata(value: object, *, depth: int, key_count: list[int]) -> None:
    if depth > MAX_METADATA_DEPTH:
        raise MetadataContractError("metadata_depth_exceeded")
    if isinstance(value, dict):
        key_count[0] += len(value)
        if key_count[0] > MAX_METADATA_KEYS:
            raise MetadataContractError("metadata_key_count_exceeded")
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise MetadataContractError("metadata_key_invalid")
            if len(key) > MAX_METADATA_KEY_LENGTH:
                raise MetadataContractError("metadata_key_length_exceeded")
            _walk_metadata(child, depth=depth + 1, key_count=key_count)
        return
    if isinstance(value, list):
        if len(value) > MAX_METADATA_LIST_LENGTH:
            raise MetadataContractError("metadata_list_length_exceeded")
        for child in value:
            _walk_metadata(child, depth=depth + 1, key_count=key_count)
        return
    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_LENGTH:
            raise MetadataContractError("metadata_string_length_exceeded")
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise MetadataContractError("metadata_number_not_finite")
        if abs(value) > MAX_METADATA_NUMBER_ABS:
            raise MetadataContractError("metadata_number_out_of_range")
        return
    if value is not None and not isinstance(value, bool):
        raise MetadataContractError("metadata_value_unsupported")


def canonical_payload(input_event: EventInput) -> str:
    """Return compact deterministic JSON for the producer-controlled fields."""

    payload = {
        "event_type": input_event.event_type,
        "metadata": input_event.metadata,
        "source_url": str(input_event.source_url),
        "timestamp": input_event.timestamp.isoformat(),
        "user_id": input_event.user_id,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def payload_hash(input_event: EventInput) -> str:
    """Hash the deterministic producer payload with SHA-256."""

    return hashlib.sha256(canonical_payload(input_event).encode("utf-8")).hexdigest()


class _FrozenDict(dict[str, MetadataValue]):
    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("canonical metadata is immutable")

    __delitem__ = __setitem__ = clear = pop = popitem = setdefault = update = _immutable  # type: ignore[assignment]

    def __ior__(self, value: object) -> _FrozenDict:  # type: ignore[override, misc]
        self._immutable(value)
        return self


class _FrozenList(list[MetadataValue]):
    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("canonical metadata is immutable")

    __delitem__ = __setitem__ = append = clear = extend = insert = pop = remove = reverse = sort = (
        _immutable
    )

    def __iadd__(self, value: object) -> _FrozenList:  # type: ignore[override, misc]
        self._immutable(value)
        return self

    def __imul__(self, value: object) -> _FrozenList:
        self._immutable(value)
        return self


def _freeze_metadata(value: MetadataValue) -> MetadataValue:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_metadata(child) for key, child in value.items()})
    if isinstance(value, list):
        return _FrozenList([_freeze_metadata(child) for child in value])
    return value


class EventInput(BaseModel):
    """Validated client-controlled event fields."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=MAX_EVENT_TYPE_LENGTH)
    timestamp: datetime
    user_id: str = Field(min_length=1, max_length=MAX_USER_ID_LENGTH)
    source_url: HttpUrl = Field(max_length=MAX_SOURCE_URL_LENGTH)
    metadata: MetadataObject

    @model_validator(mode="before")
    @classmethod
    def reject_non_json_metadata(cls, value: object) -> object:
        if not isinstance(value, dict) or "metadata" not in value:
            return value
        if _SERVER_OWNED_FIELDS.intersection(value):
            safe_value = {
                key: item for key, item in value.items() if key not in _SERVER_OWNED_FIELDS
            }
            safe_value["__event_domain_error__"] = "server_owned_field_not_allowed"
            return safe_value
        metadata = value["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError("metadata_must_be_object")
        _walk_metadata(metadata, depth=1, key_count=[0])
        return value

    @field_validator("event_type", "user_id")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("source_url")
    @classmethod
    def reject_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("source_url credentials are not allowed")
        return value

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        normalized = value.astimezone(UTC)
        if normalized > _utc_now() + MAX_FUTURE_SKEW:
            raise ValueError("timestamp exceeds permitted future skew")
        return normalized

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: MetadataObject) -> MetadataObject:
        key_count = [0]
        _walk_metadata(value, depth=1, key_count=key_count)
        try:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("metadata contains an unsupported JSON value") from error
        if len(serialized) > MAX_METADATA_BYTES:
            raise ValueError("metadata_serialized_size_exceeded")
        return value


class CanonicalEvent(BaseModel):
    """Immutable server-owned event envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    event_type: str
    timestamp: datetime
    user_id: str
    source_url: HttpUrl
    metadata: MetadataObject
    ingested_at: datetime
    schema_version: Literal[1] = 1
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_utc_times(self) -> CanonicalEvent:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be normalized to UTC")
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() != timedelta(0):
            raise ValueError("ingested_at must be normalized to UTC")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))
        return self

    @classmethod
    def from_input(
        cls,
        input_event: EventInput,
        *,
        event_id: UUID | None = None,
        ingested_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> CanonicalEvent:
        if ingested_at is not None and (
            ingested_at.tzinfo is None or ingested_at.utcoffset() is None
        ):
            raise ValueError("ingested_at must include a timezone")
        accepted_at = (ingested_at or _utc_now()).astimezone(UTC)
        key_hash = (
            hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
            if idempotency_key is not None
            else None
        )
        return cls(
            event_id=event_id or uuid4(),
            event_type=input_event.event_type,
            timestamp=input_event.timestamp,
            user_id=input_event.user_id,
            source_url=input_event.source_url,
            metadata=input_event.metadata,
            ingested_at=accepted_at,
            payload_hash=payload_hash(input_event),
            idempotency_key_hash=key_hash,
        )


class PublicEvent(BaseModel):
    """Read API representation without persistence or retry control fields."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    timestamp: datetime
    user_id: str
    source_url: HttpUrl
    metadata: MetadataObject
    ingested_at: datetime

    @classmethod
    def from_canonical(cls, event: CanonicalEvent) -> PublicEvent:
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            user_id=event.user_id,
            source_url=event.source_url,
            metadata=event.metadata,
            ingested_at=event.ingested_at,
        )


def metadata_key_count(metadata: Mapping[str, MetadataValue]) -> int:
    """Return total object-key count for diagnostics and deterministic tests."""

    count = [0]
    _walk_metadata(dict(metadata), depth=1, key_count=count)
    return count[0]
