"""Bounded process-local leaky-bucket fallback."""

from __future__ import annotations

import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from event_platform.rate_limit.models import RateDecision, RoutePolicy, schedule_request


@dataclass(slots=True)
class _State:
    next_slot: float
    last_seen: float


class LocalLeakyBucket:
    def __init__(
        self,
        *,
        max_entries: int = 1_024,
        idle_ttl_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if not 1 <= max_entries <= 100_000:
            raise ValueError("local rate-limit entry cap is outside bounds")
        if not 1 <= idle_ttl_seconds <= 86_400:
            raise ValueError("local rate-limit idle TTL is outside bounds")
        self.max_entries = max_entries
        self.idle_ttl_seconds = idle_ttl_seconds
        self._clock = clock
        self._wall_clock = wall_clock
        self._states: OrderedDict[str, _State] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._states)

    async def consume(self, key: str, policy: RoutePolicy) -> RateDecision:
        now = float(self._clock())
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _State(now, now)
                self._states[key] = state
            next_slot, allowed, remaining, delay, retry = schedule_request(
                next_slot=state.next_slot, now=now, policy=policy
            )
            state.next_slot = next_slot
            state.last_seen = now
            self._states.move_to_end(key)
            self._evict(now)
        wall_now = float(self._wall_clock())
        return RateDecision(
            allowed=allowed,
            limit=int(policy.capacity),
            remaining=remaining,
            retry_after=retry,
            reset_at=int(math.ceil(wall_now + delay)),
            backend="local",
            delay_seconds=delay,
        )

    def _evict(self, now: float) -> None:
        while self._states:
            key, state = next(iter(self._states.items()))
            if now - state.last_seen <= self.idle_ttl_seconds:
                break
            self._states.pop(key, None)
        while len(self._states) > self.max_entries:
            self._states.popitem(last=False)
