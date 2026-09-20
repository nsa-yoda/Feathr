"""Bounded, typed Elasticsearch search service with signed continuation cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import secrets
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from event_platform.domain.events import CanonicalEvent, EventInput, PublicEvent, payload_hash
from event_platform.observability.metrics import MetricsRegistry

_CURSOR_KEY = secrets.token_bytes(32)
_MAX_CURSOR_LENGTH = 512
logger = logging.getLogger("event_platform.search")


class SearchDependencyError(RuntimeError):
    """Elasticsearch is unavailable or returned an unsafe response."""


class SearchClient(Protocol):
    async def search(self, **kwargs: object) -> Mapping[str, object]: ...


class SearchCursorError(ValueError):
    """A cursor is malformed, tampered, or belongs to another query."""


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    q: str = Field(min_length=1, max_length=256)
    event_type: str | None = Field(default=None, min_length=1, max_length=128)
    user_id: str | None = Field(default=None, min_length=1, max_length=256)
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=_MAX_CURSOR_LENGTH)

    @field_validator("q", "event_type", "user_id")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("start", "end")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("search dates must be UTC")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> SearchQuery:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.end is not None:
            if self.start > self.end:
                raise ValueError("start must not exceed end")
            if self.end - self.start > timedelta(days=366):
                raise ValueError("date range exceeds maximum")
        return self


class SearchPage(BaseModel):
    items: list[PublicEvent]
    limit: int
    next_cursor: str | None
    request_id: UUID


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not value or len(value) > _MAX_CURSOR_LENGTH:
        raise SearchCursorError("cursor is invalid")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if _encode(decoded) != value:
            raise ValueError
        return decoded
    except (ValueError, UnicodeError):
        raise SearchCursorError("cursor is invalid") from None


def _scope(query: SearchQuery) -> bytes:
    return json.dumps(
        {
            "q": query.q,
            "event_type": query.event_type,
            "user_id": query.user_id,
            "start": query.start.isoformat() if query.start else None,
            "end": query.end.isoformat() if query.end else None,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def encode_search_cursor(
    sort_values: list[object], *, scope: bytes, key: bytes = _CURSOR_KEY
) -> str:
    payload = json.dumps({"s": sort_values}, separators=(",", ":"), sort_keys=True).encode()
    encoded = _encode(payload)
    signature = _encode(hmac.new(key, payload + b"." + scope, hashlib.sha256).digest())
    token = f"{encoded}.{signature}"
    if len(token) > _MAX_CURSOR_LENGTH:
        raise SearchCursorError("cursor is invalid")
    return token


def decode_search_cursor(token: str, *, scope: bytes, key: bytes = _CURSOR_KEY) -> list[object]:
    if not isinstance(token, str) or token.count(".") != 1 or len(token) > _MAX_CURSOR_LENGTH:
        raise SearchCursorError("cursor is invalid")
    payload_part, signature_part = token.split(".", 1)
    payload = _decode(payload_part)
    supplied = _decode(signature_part)
    expected = hmac.new(key, payload + b"." + scope, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise SearchCursorError("cursor is invalid")
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or set(raw) != {"s"}:
            raise ValueError
        sort_values = raw["s"]
        if not isinstance(sort_values, list) or len(sort_values) != 2:
            raise ValueError
        if any(
            isinstance(value, bool)
            or not isinstance(value, (str, int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            or (isinstance(value, str) and len(value) > 256)
            for value in sort_values
        ):
            raise ValueError
        return sort_values
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SearchCursorError("cursor is invalid") from None


class ElasticsearchSearchService:
    def __init__(
        self,
        client: SearchClient,
        *,
        alias: str = "events-search",
        cursor_key: bytes | None = None,
        previous_cursor_key: bytes | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not alias or len(alias) > 255:
            raise ValueError("search alias is invalid")
        self._client = client
        self._alias = alias
        self._cursor_key = cursor_key or _CURSOR_KEY
        self._previous_cursor_key = previous_cursor_key
        self._metrics = metrics
        if not 16 <= len(self._cursor_key) <= 64:
            raise ValueError("cursor key is invalid")

    async def search(self, query: SearchQuery, *, request_id: UUID) -> SearchPage:
        scope = _scope(query)
        search_after: list[object] | None = None
        if query.cursor is not None:
            for key in (self._cursor_key, self._previous_cursor_key):
                if key is None:
                    continue
                try:
                    search_after = decode_search_cursor(query.cursor, scope=scope, key=key)
                    break
                except SearchCursorError:
                    continue
            if search_after is None:
                raise SearchCursorError("cursor is invalid")
        filters: list[dict[str, object]] = []
        if query.event_type is not None:
            filters.append({"term": {"event_type": query.event_type}})
        if query.user_id is not None:
            filters.append({"term": {"user_id": query.user_id}})
        if query.start is not None and query.end is not None:
            filters.append({"range": {"timestamp": {"gte": query.start, "lte": query.end}}})
        body: dict[str, object] = {
            "query": {"bool": {"must": [{"match": {"metadata_text": query.q}}], "filter": filters}},
            "sort": [{"timestamp": "desc"}, {"event_id": "desc"}],
            "size": query.limit + 1,
            "_source": True,
        }
        if search_after is not None:
            body["search_after"] = search_after
        try:
            started_at = time.perf_counter()
            response = await self._client.search(index=self._alias, body=body)
            hits_container = response.get("hits")
            if not isinstance(hits_container, Mapping):
                raise ValueError
            hits = hits_container.get("hits")
            if not isinstance(hits, list):
                raise ValueError
            events: list[CanonicalEvent] = []
            sort_values_by_hit: list[list[object]] = []
            for hit in hits:
                if not isinstance(hit, Mapping):
                    raise ValueError
                source = hit.get("_source")
                hit_sort = hit.get("sort")
                if (
                    not isinstance(source, Mapping)
                    or not isinstance(hit_sort, list)
                    or len(hit_sort) != 2
                ):
                    raise ValueError
                if not all(
                    isinstance(value, (str, int, float)) and not isinstance(value, bool)
                    for value in hit_sort
                ):
                    raise ValueError
                # Search documents include derived projection fields that are not part of
                # the canonical event contract. Remove only the known derived field and
                # keep strict validation for every other unexpected response field.
                canonical_source = dict(source)
                # These fields were written by pre-ACR2 projectors. They are
                # derived storage details and are no longer part of the
                # public search document, but removing them here keeps an
                # online deployment compatible while old generations drain.
                for derived_field in (
                    "metadata_text",
                    "payload_hash",
                    "idempotency_key_hash",
                ):
                    canonical_source.pop(derived_field, None)
                # CanonicalEvent retains hashes for Mongo deduplication. The
                # search projection intentionally omits them, so reconstruct
                # the payload hash at the API boundary and never expose the
                # idempotency hash from Elasticsearch.
                canonical_input = EventInput.model_validate(
                    {
                        "event_type": canonical_source.get("event_type"),
                        "timestamp": canonical_source.get("timestamp"),
                        "user_id": canonical_source.get("user_id"),
                        "source_url": canonical_source.get("source_url"),
                        "metadata": canonical_source.get("metadata"),
                    }
                )
                canonical_source["payload_hash"] = payload_hash(canonical_input)
                canonical_source["idempotency_key_hash"] = None
                events.append(CanonicalEvent.model_validate(canonical_source))
                sort_values_by_hit.append(list(hit_sort))
            page_items = events[: query.limit]
            next_cursor = (
                encode_search_cursor(
                    sort_values_by_hit[query.limit - 1],
                    scope=scope,
                    key=self._cursor_key,
                )
                if len(events) > query.limit
                else None
            )
            if self._metrics is not None:
                self._metrics.observe_histogram(
                    "event_platform_elasticsearch_operation_latency_seconds",
                    max(0.0, time.perf_counter() - started_at),
                    {"operation": "search"},
                )
                self._metrics.inc(
                    "event_platform_elasticsearch_operations_total",
                    {"operation": "search", "outcome": "success"},
                )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            logger.warning(
                "search dependency response rejected",
                extra={
                    "event": "search.dependency_failure",
                    "error_type": type(error).__name__,
                    "classification": "malformed_response",
                },
            )
            if self._metrics is not None:
                self._metrics.observe_histogram(
                    "event_platform_elasticsearch_operation_latency_seconds",
                    max(0.0, time.perf_counter() - started_at),
                    {"operation": "search"},
                )
                self._metrics.inc(
                    "event_platform_elasticsearch_operations_total",
                    {"operation": "search", "outcome": "failure"},
                )
            raise SearchDependencyError("search dependency unavailable") from None
        except Exception as error:
            # The official client has several transport-specific exception types. Classify
            # every untrusted client failure at this boundary and never expose its details.
            logger.warning(
                "search dependency request failed",
                extra={
                    "event": "search.dependency_failure",
                    "error_type": type(error).__name__,
                    "classification": "transport_failure",
                },
            )
            if self._metrics is not None:
                self._metrics.observe_histogram(
                    "event_platform_elasticsearch_operation_latency_seconds",
                    max(0.0, time.perf_counter() - started_at),
                    {"operation": "search"},
                )
                self._metrics.inc(
                    "event_platform_elasticsearch_operations_total",
                    {"operation": "search", "outcome": "failure"},
                )
            raise SearchDependencyError("search dependency unavailable") from None
        return SearchPage(
            items=[PublicEvent.from_canonical(item) for item in page_items],
            limit=query.limit,
            next_cursor=next_cursor,
            request_id=request_id,
        )
