"""Typed health state and safe dependency probe boundary."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from event_platform.observability.metrics import MetricName, MetricsRegistry

ComponentState = Literal["healthy", "degraded", "unhealthy"]
HealthDetail = Literal["ok", "degraded", "unavailable", "not_configured", "probe_failed", "unknown"]
Probe = Callable[[], ComponentState | bool | str | Awaitable[ComponentState | bool | str]]
logger = logging.getLogger("event_platform.health")


class ComponentHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: ComponentState
    detail: HealthDetail


class HealthComponents(BaseModel):
    model_config = ConfigDict(frozen=True)

    mongo: ComponentHealth
    elasticsearch: ComponentHealth
    redis: ComponentHealth
    queue: ComponentHealth
    persistence_worker: ComponentHealth
    search_projector: ComponentHealth


class HealthSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComponentState
    components: HealthComponents


class HealthRegistry:
    """Owns bounded component probes; probe details never contain exception text."""

    _NAMES = ("mongo", "elasticsearch", "redis", "queue", "persistence_worker", "search_projector")

    def __init__(
        self,
        metrics: MetricsRegistry | None = None,
        *,
        probe_timeout: float = 0.5,
        overall_timeout: float = 1.0,
    ) -> None:
        if probe_timeout <= 0 or overall_timeout <= 0:
            raise ValueError("health probe deadlines must be positive")
        self._probes: dict[str, Probe] = {}
        self._metrics = metrics
        self._probe_timeout = probe_timeout
        self._overall_timeout = overall_timeout

    def set_probe(self, name: str, probe: Probe) -> None:
        if name not in self._NAMES:
            raise ValueError("unsupported health component")
        self._probes[name] = probe

    async def snapshot(self) -> HealthSnapshot:
        async def collect() -> dict[str, ComponentHealth]:
            values = await asyncio.gather(*(self._probe(name) for name in self._NAMES))
            return dict(zip(self._NAMES, values, strict=True))

        try:
            results = await asyncio.wait_for(collect(), timeout=self._overall_timeout)
        except TimeoutError:
            results = {
                name: ComponentHealth(state="unhealthy", detail="probe_failed")
                for name in self._NAMES
            }
        status: ComponentState = "healthy"
        if any(item.state == "unhealthy" for item in results.values()):
            status = "unhealthy"
        elif any(item.state == "degraded" for item in results.values()):
            status = "degraded"
        return HealthSnapshot(status=status, components=HealthComponents(**results))

    async def _probe(self, name: str) -> ComponentHealth:
        probe = self._probes.get(name)
        if probe is None:
            return ComponentHealth(state="degraded", detail="not_configured")
        try:
            value = probe()
            if inspect.isawaitable(value):
                value = await asyncio.wait_for(value, timeout=self._probe_timeout)
            result = _coerce(value)
            self._record_metric(name, result.state)
            return result
        except Exception as error:
            logger.warning(
                "health probe failed",
                extra={
                    "event": "health.probe_failed",
                    "component": name,
                    "error_type": type(error).__name__,
                    "state": "unhealthy",
                },
            )
            self._record_metric(name, "unhealthy")
            return ComponentHealth(state="unhealthy", detail="probe_failed")

    def _record_metric(self, name: str, state: ComponentState) -> None:
        if self._metrics is None:
            return
        family = cast(
            MetricName,
            {
                "mongo": "event_platform_mongo_operations_total",
                "elasticsearch": "event_platform_elasticsearch_operations_total",
                "redis": "event_platform_redis_operations_total",
                "queue": "event_platform_queue_operations_total",
                "persistence_worker": "event_platform_worker_operations_total",
                "search_projector": "event_platform_elasticsearch_operations_total",
            }[name],
        )
        outcome = (
            "success" if state == "healthy" else "degraded" if state == "degraded" else "failure"
        )
        self._metrics.inc(family, {"outcome": outcome})

    async def ready(self) -> tuple[bool, HealthSnapshot]:
        snapshot = await self.snapshot()
        required = ("mongo", "queue", "persistence_worker")
        ready = all(getattr(snapshot.components, name).state == "healthy" for name in required)
        return ready, snapshot


def _coerce(value: ComponentState | bool | str) -> ComponentHealth:
    if value is True or value == "healthy":
        return ComponentHealth(state="healthy", detail="ok")
    if value == "degraded":
        return ComponentHealth(state="degraded", detail="degraded")
    if value is False or value == "unhealthy":
        return ComponentHealth(state="unhealthy", detail="unavailable")
    return ComponentHealth(state="degraded", detail="unknown")
