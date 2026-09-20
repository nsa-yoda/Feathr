"""Durable request idempotency registry with a bounded in-memory test adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError, PyMongoError


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    outcome: str
    event_id: UUID


class IdempotencyRegistryError(RuntimeError):
    """Safe dependency failure for the idempotency boundary."""


class IdempotencyRegistry(Protocol):
    async def reserve(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        fingerprint: str,
        event_id: UUID,
        now: datetime,
        replay_window: timedelta,
    ) -> IdempotencyDecision: ...

    async def complete(self, *, scope: str, key: str, operation: str, event_id: UUID) -> None: ...


def registry_id(scope: str, key: str, operation: str) -> str:
    return hashlib.sha256(f"{scope}\x00{operation}\x00{key}".encode()).hexdigest()


class InMemoryIdempotencyRegistry:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, object]] = {}

    async def reserve(self, **kwargs: object) -> IdempotencyDecision:
        now = kwargs["now"]
        replay_window = kwargs["replay_window"]
        if not isinstance(now, datetime) or not isinstance(replay_window, timedelta):
            raise TypeError("invalid idempotency timing")
        identifier = registry_id(str(kwargs["scope"]), str(kwargs["key"]), str(kwargs["operation"]))
        existing = self._records.get(identifier)
        event_id = kwargs["event_id"]
        if not isinstance(event_id, UUID):
            raise TypeError("event_id must be UUID")
        if existing is not None:
            if existing["fingerprint"] != kwargs["fingerprint"]:
                return IdempotencyDecision("conflict", event_id)
            if existing["status"] == "completed":
                return IdempotencyDecision("replay", UUID(str(existing["event_id"])))
            created_at = existing["created_at"]
            if isinstance(created_at, datetime) and now - created_at < replay_window:
                return IdempotencyDecision("in_flight", UUID(str(existing["event_id"])))
        self._records[identifier] = {
            "fingerprint": kwargs["fingerprint"],
            "event_id": str(event_id),
            "status": "reserved",
            "created_at": now,
        }
        return IdempotencyDecision("new", event_id)

    async def complete(self, *, scope: str, key: str, operation: str, event_id: UUID) -> None:
        record = self._records.get(registry_id(scope, key, operation))
        if record is not None and record["event_id"] == str(event_id):
            record["status"] = "completed"


class MongoIdempotencyRegistry:
    def __init__(self, collection: AsyncCollection[dict[str, object]]) -> None:
        self._collection = collection

    async def reserve(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        fingerprint: str,
        event_id: UUID,
        now: datetime,
        replay_window: timedelta,
    ) -> IdempotencyDecision:
        identifier = registry_id(scope, key, operation)
        try:
            document = await self._collection.find_one({"_id": identifier})
            if document is None:
                await self._collection.insert_one(
                    {
                        "_id": identifier,
                        "scope": scope,
                        "operation": operation,
                        "fingerprint": fingerprint,
                        "event_id": str(event_id),
                        "status": "reserved",
                        "created_at": now,
                    }
                )
                return IdempotencyDecision("new", event_id)
        except DuplicateKeyError:
            document = await self._collection.find_one({"_id": identifier})
        except PyMongoError:
            raise IdempotencyRegistryError("reserve_idempotency") from None
        if not isinstance(document, dict):
            raise IdempotencyRegistryError("reserve_idempotency")
        if document.get("fingerprint") != fingerprint:
            return IdempotencyDecision("conflict", event_id)
        stored_event = UUID(str(document.get("event_id")))
        if document.get("status") == "completed":
            return IdempotencyDecision("replay", stored_event)
        created_at = document.get("created_at")
        if isinstance(created_at, datetime) and now - created_at < replay_window:
            return IdempotencyDecision("in_flight", stored_event)
        try:
            await self._collection.update_one(
                {"_id": identifier, "fingerprint": fingerprint},
                {"$set": {"event_id": str(event_id), "created_at": now, "status": "reserved"}},
            )
        except PyMongoError:
            raise IdempotencyRegistryError("reserve_idempotency") from None
        return IdempotencyDecision("new", event_id)

    async def complete(self, *, scope: str, key: str, operation: str, event_id: UUID) -> None:
        try:
            await self._collection.update_one(
                {"_id": registry_id(scope, key, operation), "event_id": str(event_id)},
                {"$set": {"status": "completed", "completed_at": datetime.now(UTC)}},
            )
        except PyMongoError:
            raise IdempotencyRegistryError("complete_idempotency") from None
