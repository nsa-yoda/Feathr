"""Asynchronous event ingestion route."""

import logging
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from event_platform.api.problems import ProblemResponse
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.queue import InProcessQueue, QueueFull
from event_platform.storage.idempotency import IdempotencyRegistryError

router = APIRouter(tags=["events"])
logger = logging.getLogger("event_platform.queue")
IdempotencyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=256,
        pattern=r"^[\x21-\x7e]+$",
    ),
]


class IngestResponse(BaseModel):
    event_id: UUID
    status: Literal["queued"]
    request_id: UUID


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
    responses={
        422: {
            "description": "Request validation failed",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        503: {
            "description": "Queue capacity is temporarily unavailable",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        409: {
            "description": "Idempotency key is already in flight or conflicts with another request",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
    },
)
async def ingest_event(
    event: EventInput,
    request: Request,
    idempotency_key: IdempotencyHeader = None,
) -> IngestResponse:
    request_id = UUID(str(getattr(request.state, "request_id", uuid4())))
    canonical = CanonicalEvent.from_input(event, idempotency_key=idempotency_key)
    registry = getattr(request.app.state, "idempotency_registry", None)
    scope = str(getattr(request.state, "client_scope", "anonymous"))
    if idempotency_key is not None and registry is not None:
        try:
            decision = await registry.reserve(
                scope=scope,
                key=idempotency_key,
                operation="events.create",
                fingerprint=canonical.payload_hash,
                event_id=canonical.event_id,
                now=canonical.ingested_at,
                replay_window=timedelta(
                    seconds=request.app.state.settings.idempotency_replay_window_seconds
                ),
            )
        except IdempotencyRegistryError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="idempotency registry is temporarily unavailable",
                headers={"Retry-After": "1"},
            ) from None
        if decision.outcome == "replay":
            return IngestResponse(
                event_id=decision.event_id,
                status="queued",
                request_id=request_id,
            )
        if decision.outcome == "conflict":
            raise HTTPException(status_code=409, detail="idempotency key conflicts with request")
        if decision.outcome == "in_flight":
            raise HTTPException(status_code=409, detail="idempotency request is already in flight")
    queue: InProcessQueue = request.app.state.queue
    try:
        await queue.send(
            canonical.model_dump(mode="json"),
            message_id=str(canonical.event_id),
            operation_id=getattr(request.state, "operation_id", None),
        )
    except QueueFull:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="queue capacity is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
    if idempotency_key is not None and registry is not None:
        try:
            await registry.complete(
                scope=scope,
                key=idempotency_key,
                operation="events.create",
                event_id=canonical.event_id,
            )
        except IdempotencyRegistryError:
            logger.warning(
                "idempotency completion deferred",
                extra={"event": "idempotency.completion_deferred", "outcome": "accepted"},
            )
    logger.info(
        "event enqueued",
        extra={
            "event": "queue.enqueue",
            "request_id": str(request_id),
            "operation_id": str(getattr(request.state, "operation_id", "")),
            "outcome": "accepted",
        },
    )
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is not None:
        metrics.inc("event_platform_queue_operations_total", {"outcome": "accepted"})
    return IngestResponse(event_id=canonical.event_id, status="queued", request_id=request_id)
