"""Lightweight consolidated read-only snapshot for the operational visualizer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from event_platform.cache.realtime import (
    DEFAULT_WINDOW_MINUTES,
    RealtimeStatsResponse,
    RealtimeStatsResultLimit,
    RealtimeStatsService,
)
from event_platform.observability.health import HealthSnapshot
from event_platform.storage.mongo import MongoDependencyError

router = APIRouter(tags=["operations"])


class VisualizerSnapshot(BaseModel):
    """Bounded snapshot assembled from in-process metrics and cached analytics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    health: HealthSnapshot
    metrics: str
    realtime: RealtimeStatsResponse | None = None
    realtime_cache: str = "UNAVAILABLE"
    realtime_error: str | None = None


def _request_uuid(request: Request) -> UUID:
    return UUID(str(getattr(request.state, "request_id", uuid4())))


@router.get("/operations/visualizer", response_model=VisualizerSnapshot)
async def visualizer_snapshot(
    request: Request,
    window_minutes: Annotated[int, Query(ge=1, le=60)] = DEFAULT_WINDOW_MINUTES,
) -> VisualizerSnapshot:
    """Return one cheap dashboard read, avoiding a request fan-out per tick."""

    from event_platform.observability.metrics import MetricsRegistry

    registry = getattr(request.app.state, "health", None)
    metrics = getattr(request.app.state, "metrics", None)
    if registry is None or not isinstance(metrics, MetricsRegistry):
        raise RuntimeError("visualizer dependencies are not initialized")

    health = await registry.snapshot()
    realtime: RealtimeStatsResponse | None = None
    cache_outcome = "UNAVAILABLE"
    realtime_error: str | None = None
    settings = getattr(request.app.state, "settings", None)
    service = getattr(request.app.state, "realtime_stats_service", None)
    if service is None:
        store = getattr(request.app.state, "event_store", None)
        if store is not None:
            service = RealtimeStatsService(
                store=store,
                cache=getattr(request.app.state, "realtime_cache", None),
                ttl_seconds=getattr(settings, "realtime_cache_ttl_seconds", 10),
                max_event_types=getattr(settings, "realtime_max_event_types", 1_000),
                metrics=metrics,
            )
            request.app.state.realtime_stats_service = service
    if service is not None:
        try:
            realtime, cache_outcome = await service.get(
                window_minutes=window_minutes,
                request_id=_request_uuid(request),
            )
        except RealtimeStatsResultLimit:
            realtime_error = "result_limit"
        except (MongoDependencyError, ValueError):
            realtime_error = "canonical_unavailable"
    return VisualizerSnapshot(
        generated_at=datetime.now(UTC),
        health=cast(HealthSnapshot, health),
        metrics=metrics.render(),
        realtime=realtime,
        realtime_cache=cache_outcome,
        realtime_error=realtime_error,
    )
