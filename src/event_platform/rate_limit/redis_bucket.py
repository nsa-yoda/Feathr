"""Atomic Redis token bucket adapter."""

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


_TOKEN_BUCKET_SCRIPT = """
local tokens_raw = redis.call('HGET', KEYS[1], 'tokens')
local updated_raw = redis.call('HGET', KEYS[1], 'updated')
local tokens = tonumber(tokens_raw)
local updated = tonumber(updated_raw)
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
if not tokens_raw and not updated_raw then
  tokens = capacity
  updated = now
elseif not tokens or not updated then
  return {-1, 0, 0, 0}
end
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill)
local allowed = 0
local retry = 0
local reset = now + 1
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry = math.max(1, math.ceil((cost - tokens) / refill))
  reset = now + retry
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], ttl)
return {allowed, math.floor(tokens), retry, math.ceil(reset)}
"""


class RateLimitUnavailable(RuntimeError):
    def __init__(self, operation: str) -> None:
        super().__init__(operation)
        self.operation = operation


class RedisTokenBucket:
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
        try:
            result = await cast(_EvalClient, self._client).eval(
                _TOKEN_BUCKET_SCRIPT,
                1,
                f"{self._key_prefix}{key}",
                str(now),
                str(policy.capacity),
                str(policy.refill_per_second),
                str(policy.cost),
                str(max(1, int(math.ceil(policy.capacity / policy.refill_per_second)) * 2)),
            )
        except (RedisError, OSError, TimeoutError):
            raise RateLimitUnavailable("eval") from None
        if not isinstance(result, list | tuple) or len(result) != 4:
            raise RateLimitUnavailable("decode")
        if any(type(value) is not int for value in result):
            raise RateLimitUnavailable("decode")
        try:
            allowed, remaining, retry, reset = result
        except (OverflowError, TypeError, ValueError):
            raise RateLimitUnavailable("decode") from None
        max_ttl = max(1, int(math.ceil(policy.capacity / policy.refill_per_second)) * 2)
        if (
            allowed not in {0, 1}
            or not 0 <= remaining <= int(policy.capacity)
            or (allowed == 1 and retry != 0)
            or (allowed == 0 and retry < 1)
            or reset < int(math.ceil(now))
            or reset > int(math.ceil(now + max_ttl))
        ):
            raise RateLimitUnavailable("decode")
        return RateDecision(
            allowed=bool(allowed),
            limit=int(policy.capacity),
            remaining=remaining,
            retry_after=retry,
            reset_at=reset,
            backend="redis",
        )
