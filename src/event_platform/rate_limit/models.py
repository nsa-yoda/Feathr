"""Typed rate-limit policies and deterministic token-bucket math."""

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
        ):
            raise ValueError("rate-limit decision values are invalid")


def consume_tokens(
    *,
    tokens: float,
    last_refill: float,
    now: float,
    policy: RoutePolicy,
) -> tuple[float, float, bool, int, int]:
    """Refill and consume one bucket, returning state and retry metadata."""

    elapsed = max(0.0, now - last_refill)
    available = min(policy.capacity, tokens + elapsed * policy.refill_per_second)
    if available >= policy.cost:
        remaining = available - policy.cost
        return remaining, now, True, 0, int(math.ceil(now + 1))
    wait = (policy.cost - available) / policy.refill_per_second
    return available, now, False, max(1, int(math.ceil(wait))), int(math.ceil(now + wait))
