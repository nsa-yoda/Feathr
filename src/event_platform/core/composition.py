"""Typed application-service boundary for lifespan composition and route tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from event_platform.observability.health import HealthRegistry
from event_platform.observability.metrics import MetricsRegistry
from event_platform.queue import InProcessQueue


class EventStorePort(Protocol):
    async def insert(self, event: object) -> None: ...


class SearchServicePort(Protocol):
    async def search(self, query: object, *, request_id: object) -> object: ...


@dataclass(slots=True)
class ApplicationServices:
    """Explicit required/optional runtime dependencies owned by the app."""

    queue: InProcessQueue
    metrics: MetricsRegistry
    health: HealthRegistry
    event_store: EventStorePort | None = None
    search_service: SearchServicePort | None = None
    realtime_stats_service: object | None = None
    rebuild_store: object | None = None


def build_application_services(
    *, queue: InProcessQueue, metrics: MetricsRegistry, health: HealthRegistry
) -> ApplicationServices:
    return ApplicationServices(queue=queue, metrics=metrics, health=health)
