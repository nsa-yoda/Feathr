"""Typed rate-limit policies and deterministic leaky-bucket scheduling math."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class RouteClass(StrEnum):
    INGESTION = "ingestion"
    NORMAL_READ = "normal-read"
    EXPENSIVE_READ = "expensive-read"
    OPS = "ops"
    EXEMPT = "exempt"


MIN_REFILL_PER_SECOND = 0.001


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    route_class: RouteClass
    capacity: int
    refill_per_second: float
    cost: int = 1
    exempt: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.route_class, RouteClass)
            or type(self.exempt) is not bool
            or type(self.capacity) is not int
            or isinstance(self.capacity, bool)
            or self.capacity <= 0
            or type(self.cost) is not int
            or isinstance(self.cost, bool)
            or self.cost <= 0
            or not math.isfinite(self.refill_per_second)
            or self.refill_per_second < MIN_REFILL_PER_SECOND
        ):
            raise ValueError("rate-limit policy values must be positive")
        if self.cost > self.capacity:
            raise ValueError("rate-limit cost cannot exceed capacity")


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int
    backend: Literal["redis", "local"]
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if (
            type(self.limit) is not int
            or type(self.remaining) is not int
            or type(self.retry_after) is not int
            or type(self.reset_at) is not int
            or self.limit <= 0
            or not 0 <= self.remaining <= self.limit
            or self.retry_after < 0
            or self.reset_at < 0
            or self.backend not in {"redis", "local"}
            or not math.isfinite(self.delay_seconds)
            or self.delay_seconds < 0
        ):
            raise ValueError("rate-limit decision values are invalid")


def schedule_request(
    *,
    next_slot: float,
    now: float,
    policy: RoutePolicy,
) -> tuple[float, bool, int, float, int]:
    """Reserve one leak slot or reject only when the bounded backlog is full."""

    interval = policy.cost / policy.refill_per_second
    scheduled = max(now, next_slot)
    delay = max(0.0, scheduled - now)
    queued_ahead = max(0, int(math.ceil((delay / interval) - 1e-9)))
    if queued_ahead >= policy.capacity:
        retry = max(interval, delay - ((policy.capacity - 1) * interval))
        return next_slot, False, 0, 0.0, max(1, int(math.ceil(retry)))
    queue_depth = queued_ahead + 1
    return scheduled + interval, True, policy.capacity - queue_depth, delay, 0
