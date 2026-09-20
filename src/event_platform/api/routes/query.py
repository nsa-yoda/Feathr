"""Canonical event query API with bounded signed keyset cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from event_platform.api.problems import ProblemResponse
from event_platform.domain.events import CanonicalEvent, PublicEvent
from event_platform.storage.mongo import EventQuery, MongoDependencyError

router = APIRouter(tags=["events"])
_CURSOR_KEY = secrets.token_bytes(32)
_MAX_CURSOR_LENGTH = 512


class CursorError(ValueError):
    """The public cursor is malformed, unsupported, or tampered."""


class EventCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(alias="v", strict=True)
    timestamp: datetime = Field(alias="t")
    event_id: UUID = Field(alias="i")


class EventPage(BaseModel):
    items: list[PublicEvent]
    limit: int
    next_cursor: str | None
    request_id: UUID


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_part(value: str) -> bytes:
    if not value or len(value) > _MAX_CURSOR_LENGTH:
        raise CursorError("cursor is invalid")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if _encode_part(decoded) != value:
            raise ValueError
        return decoded
    except ValueError:
        raise CursorError("cursor is invalid") from None


def _scope_bytes(
    event_type: str | None = None,
    user_id: str | None = None,
    source_url: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> bytes:
    return json.dumps(
        {
            "event_type": event_type,
            "user_id": user_id,
            "source_url": source_url,
            "start": start.isoformat() if start is not None else None,
            "end": end.isoformat() if end is not None else None,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def encode_cursor(
    timestamp: datetime,
    event_id: UUID,
    *,
    scope: bytes = b"",
    key: bytes = _CURSOR_KEY,
) -> str:
    """Encode only the public keyset fields in a signed URL-safe token."""

    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise CursorError("cursor timestamp must be UTC")
    payload = json.dumps(
        {"v": 1, "t": timestamp.astimezone(UTC).isoformat(), "i": str(event_id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _encode_part(payload)
    signature = _encode_part(hmac.new(key, payload + b"." + scope, hashlib.sha256).digest())
    token = f"{encoded_payload}.{signature}"
    if len(token) > _MAX_CURSOR_LENGTH:
        raise CursorError("cursor is invalid")
    return token


def decode_cursor(token: str, *, scope: bytes = b"", key: bytes = _CURSOR_KEY) -> EventCursor:
    """Validate a cursor without exposing parser or signature details."""

    if not isinstance(token, str) or len(token) > _MAX_CURSOR_LENGTH or token.count(".") != 1:
        raise CursorError("cursor is invalid")
    payload_part, signature_part = token.split(".", 1)
    payload = _decode_part(payload_part)
    supplied_signature = _decode_part(signature_part)
    expected_signature = hmac.new(key, payload + b"." + scope, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise CursorError("cursor is invalid")
    try:
        raw = json.loads(payload)
        cursor = EventCursor.model_validate(raw)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        raise CursorError("cursor is invalid") from None
    if (
        cursor.version != 1
        or cursor.timestamp.tzinfo is None
        or cursor.timestamp.utcoffset() != UTC.utcoffset(cursor.timestamp)
    ):
        raise CursorError("cursor is invalid")
    if set(raw) != {"v", "t", "i"}:
        raise CursorError("cursor is invalid")
    return cursor


def _request_uuid(request: Request) -> UUID:
    return UUID(str(getattr(request.state, "request_id", secrets.token_hex(16))))


def _cursor_keys(request: Request) -> tuple[bytes, ...]:
    keys = getattr(request.app.state, "cursor_keys", None)
    return keys if isinstance(keys, tuple) and keys else (_CURSOR_KEY,)


def _invalid_query() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="query input is invalid",
    )


@router.get(
    "/events",
    response_model=EventPage,
    responses={
        422: {
            "description": "Request validation failed",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        503: {
            "description": "Canonical event storage is unavailable",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
    },
)
async def query_events(
    request: Request,
    event_type: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    user_id: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
    source_url: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=_MAX_CURSOR_LENGTH)] = None,
) -> EventPage:
    request_id = _request_uuid(request)
    try:
        query = EventQuery(
            event_type=event_type,
            user_id=user_id,
            source_url=source_url,
            timestamp_from=start,
            timestamp_to=end,
            limit=limit + 1,
        )
    except (ValidationError, ValueError):
        raise _invalid_query() from None
    scope = _scope_bytes(
        query.event_type,
        query.user_id,
        query.source_url,
        query.timestamp_from,
        query.timestamp_to,
    )
    if cursor is not None:
        continuation = None
        for key in _cursor_keys(request):
            try:
                continuation = decode_cursor(cursor, scope=scope, key=key)
                break
            except CursorError:
                continue
        if continuation is None:
            raise _invalid_query() from None
        query = query.model_copy(
            update={
                "after_timestamp": continuation.timestamp,
                "after_event_id": continuation.event_id,
            }
        )

    store = getattr(request.app.state, "event_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="canonical event storage is temporarily unavailable",
            headers={"Retry-After": "1"},
        )
    try:
        events: list[CanonicalEvent] = [event async for event in store.query(query)]
    except MongoDependencyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="canonical event storage is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
    page_items = events[:limit]
    next_cursor = (
        encode_cursor(
            page_items[-1].timestamp,
            page_items[-1].event_id,
            scope=scope,
            key=_cursor_keys(request)[0],
        )
        if len(events) > limit
        else None
    )
    return EventPage(
        items=[PublicEvent.from_canonical(item) for item in page_items],
        limit=limit,
        next_cursor=next_cursor,
        request_id=request_id,
    )
