"""Atomic Redis leaky-bucket reservation adapter."""

from __future__ import annotations

import math
import time
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from event_platform.rate_limit.models import RateDecision, RoutePolicy


class _EvalClient(Protocol):
    def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Awaitable[object]: ...


_LEAKY_BUCKET_SCRIPT = """
local next_raw = redis.call('GET', KEYS[1])
local next_slot = tonumber(next_raw)
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local interval = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
if next_raw and not next_slot then
  return {-1, 0, 0, 0, 0}
end
next_slot = math.max(now, next_slot or now)
local delay = math.max(0, next_slot - now)
local queued_ahead = math.ceil(delay / interval)
if queued_ahead >= capacity then
  local retry = math.max(1, next_slot - now - ((capacity - 1) * interval))
  return {0, 0, 0, retry, next_slot}
end
local remaining = capacity - queued_ahead - 1
redis.call('SET', KEYS[1], next_slot + interval, 'PX', ttl)
return {1, remaining, delay, 0, next_slot}
"""


class RateLimitUnavailable(RuntimeError):
    def __init__(self, operation: str) -> None:
        super().__init__(operation)
        self.operation = operation


class RedisLeakyBucket:
    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str = "rate-limit:v1:",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._clock = clock

    async def consume(self, key: str, policy: RoutePolicy) -> RateDecision:
        now = self._clock()
        interval_ms = max(1, int(math.ceil((policy.cost / policy.refill_per_second) * 1000)))
        now_ms = int(math.floor(now * 1000))
        try:
            result = await cast(_EvalClient, self._client).eval(
                _LEAKY_BUCKET_SCRIPT,
                1,
                f"{self._key_prefix}{key}",
                str(now_ms),
                str(policy.capacity),
                str(interval_ms),
                str(max(1_000, policy.capacity * interval_ms * 2)),
            )
        except (RedisError, OSError, TimeoutError):
            raise RateLimitUnavailable("eval") from None
        if not isinstance(result, list | tuple) or len(result) != 5:
            raise RateLimitUnavailable("decode")
        if any(type(value) is not int for value in result):
            raise RateLimitUnavailable("decode")
        try:
            allowed, remaining, delay_ms, retry_ms, release_ms = result
        except (OverflowError, TypeError, ValueError):
            raise RateLimitUnavailable("decode") from None
        max_delay_ms = policy.capacity * interval_ms
        if (
            allowed not in {0, 1}
            or not 0 <= remaining <= int(policy.capacity)
            or delay_ms < 0
            or delay_ms > max_delay_ms
            or (allowed == 1 and retry_ms != 0)
            or (allowed == 0 and retry_ms < 1)
            or release_ms < now_ms
            or release_ms > now_ms + max_delay_ms
        ):
            raise RateLimitUnavailable("decode")
        return RateDecision(
            allowed=bool(allowed),
            limit=int(policy.capacity),
            remaining=remaining,
            retry_after=max(0, int(math.ceil(retry_ms / 1000))),
            reset_at=int(math.ceil(release_ms / 1000)),
            backend="redis",
            delay_seconds=delay_ms / 1000,
        )
