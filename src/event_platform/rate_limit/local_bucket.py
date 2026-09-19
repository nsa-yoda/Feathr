"""Bounded process-local token-bucket fallback."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from event_platform.rate_limit.models import RateDecision, RoutePolicy, consume_tokens


@dataclass(slots=True)
class _State:
    tokens: float
    last_refill: float
    last_seen: float


class LocalTokenBucket:
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
                state = _State(policy.capacity, now, now)
                self._states[key] = state
            tokens, last_refill, allowed, retry, reset = consume_tokens(
                tokens=state.tokens, last_refill=state.last_refill, now=now, policy=policy
            )
            state.tokens = tokens
            state.last_refill = last_refill
            state.last_seen = now
            self._states.move_to_end(key)
            self._evict(now)
        wall_now = float(self._wall_clock())
        return RateDecision(
            allowed=allowed,
            limit=int(policy.capacity),
            remaining=max(0, int(tokens)),
            retry_after=retry,
            reset_at=int(wall_now + max(1, reset - now)),
            backend="local",
        )

    def _evict(self, now: float) -> None:
        expired = [
            key
            for key, state in self._states.items()
            if now - state.last_seen > self.idle_ttl_seconds
        ]
        for key in expired:
            self._states.pop(key, None)
        while len(self._states) > self.max_entries:
            self._states.popitem(last=False)
