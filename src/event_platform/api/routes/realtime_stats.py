"""Read-only rolling statistics backed by canonical Mongo and optional Redis cache."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from event_platform.api.problems import ProblemResponse
from event_platform.cache.realtime import (
    DEFAULT_WINDOW_MINUTES,
    RealtimeStatsResponse,
    RealtimeStatsResultLimit,
    RealtimeStatsService,
)
from event_platform.storage.mongo import MongoDependencyError

router = APIRouter(tags=["events"])


def _request_uuid(request: Request) -> UUID:
    return UUID(str(getattr(request.state, "request_id", uuid4())))


@router.get(
    "/events/stats/realtime",
    response_model=RealtimeStatsResponse,
    responses={
        422: {
            "description": "Realtime statistics query validation failed",
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
async def realtime_stats(
    request: Request,
    response: Response,
    window_minutes: Annotated[int | None, Query(ge=1, le=60)] = None,
) -> RealtimeStatsResponse:
    settings = getattr(request.app.state, "settings", None)
    configured_window = cast(
        int, getattr(settings, "realtime_default_window_minutes", DEFAULT_WINDOW_MINUTES)
    )
    effective_window = window_minutes if window_minutes is not None else configured_window
    service = getattr(request.app.state, "realtime_stats_service", None)
    if service is None:
        store = getattr(request.app.state, "event_store", None)
        if store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="canonical event storage is temporarily unavailable",
                headers={"Retry-After": "1"},
            )
        service = RealtimeStatsService(
            store=store,
            cache=getattr(request.app.state, "realtime_cache", None),
            ttl_seconds=getattr(settings, "realtime_cache_ttl_seconds", 10),
            max_event_types=getattr(settings, "realtime_max_event_types", 1_000),
            metrics=getattr(request.app.state, "metrics", None),
        )
        request.app.state.realtime_stats_service = service
    try:
        result, cache_outcome = await service.get(
            window_minutes=effective_window,
            request_id=_request_uuid(request),
        )
    except RealtimeStatsResultLimit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="realtime statistics result exceeds the bounded event-type limit",
        ) from None
    except (MongoDependencyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="canonical event storage is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
    response.headers["X-Cache"] = cache_outcome
    return result
