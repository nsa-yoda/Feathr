"""Mongo-backed search projection checkpoint storage."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from bson import BSON
from bson.errors import InvalidDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import PyMongoError

from event_platform.search.projection import (
    SAFE_FAILURE_CODES,
    ProjectionCheckpoint,
    ProjectionError,
    ProjectionState,
)


class CheckpointDependencyError(ProjectionError):
    def __init__(self) -> None:
        super().__init__("checkpoint_unavailable", transient=True)


class MongoProjectionCheckpointStore:
    def __init__(self, collection: AsyncCollection[Mapping[str, object]]) -> None:
        self._collection = collection

    async def load(self, projector: str) -> ProjectionCheckpoint | None:
        try:
            document = await self._collection.find_one({"projector": projector})
        except PyMongoError:
            raise CheckpointDependencyError() from None
        if document is None:
            return None
        try:
            token = document.get("resume_token")
            if not isinstance(token, Mapping) or not token:
                raise ValueError
            _assert_bson_safe(token)
            updated_at = document["updated_at"]
            if not isinstance(updated_at, datetime):
                raise ValueError
            last_event = document.get("last_projected_event_at")
            if last_event is not None and not isinstance(last_event, datetime):
                raise ValueError
            state_value = document.get("state", "running")
            if state_value not in {
                "starting",
                "running",
                "retrying",
                "degraded",
                "reconciliation_required",
                "stopped",
            }:
                raise ValueError
            state = cast(ProjectionState, state_value)
            failure_code = document.get("failure_code")
            if failure_code is not None and (
                not isinstance(failure_code, str) or failure_code not in SAFE_FAILURE_CODES
            ):
                raise ValueError
            return ProjectionCheckpoint(
                projector=projector,
                resume_token=dict(token),
                state=state,
                updated_at=_utc(updated_at),
                last_projected_event_at=_utc(last_event) if last_event else None,
                failure_code=failure_code,
            )
        except (KeyError, TypeError, ValueError):
            raise ProjectionError("checkpoint_invalid") from None

    async def save(self, checkpoint: ProjectionCheckpoint) -> None:
        try:
            _assert_bson_safe(checkpoint.resume_token)
            await self._collection.replace_one(
                {"projector": checkpoint.projector},
                {
                    "projector": checkpoint.projector,
                    "resume_token": dict(checkpoint.resume_token),
                    "state": checkpoint.state,
                    "updated_at": _utc(checkpoint.updated_at),
                    "last_projected_event_at": (
                        _utc(checkpoint.last_projected_event_at)
                        if checkpoint.last_projected_event_at
                        else None
                    ),
                    "failure_code": checkpoint.failure_code,
                },
                upsert=True,
            )
        except PyMongoError:
            raise CheckpointDependencyError() from None
        except (TypeError, ValueError):
            raise ProjectionError("checkpoint_invalid") from None


def _assert_bson_safe(token: Mapping[str, object]) -> None:
    if not token:
        raise ValueError("resume token must not be empty")
    try:
        BSON.encode(dict(token))
    except (InvalidDocument, TypeError, ValueError) as error:
        # BSON's encoder raises several concrete value/type errors. Do not leak them.
        raise ValueError("resume token is not BSON safe") from error


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
