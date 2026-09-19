"""Asynchronous event ingestion route."""

import logging
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from event_platform.api.problems import ProblemResponse
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.queue import InProcessQueue, QueueFull

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
    },
)
async def ingest_event(
    event: EventInput,
    request: Request,
    idempotency_key: IdempotencyHeader = None,
) -> IngestResponse:
    request_id = UUID(str(getattr(request.state, "request_id", uuid4())))
    canonical = CanonicalEvent.from_input(event, idempotency_key=idempotency_key)
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
