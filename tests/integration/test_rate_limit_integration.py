from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from redis.asyncio import Redis

from event_platform.rate_limit import RedisLeakyBucket, RouteClass, RoutePolicy
from event_platform.rate_limit.redis_bucket import RateLimitUnavailable

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_redis_leaky_bucket_is_atomic_and_route_isolated() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL is not configured")
    redis = Redis.from_url(redis_url)
    key = f"feature014-{uuid.uuid4().hex}"
    try:
        clock = [1_000.0]
        bucket = RedisLeakyBucket(redis, key_prefix=f"{key}:", clock=lambda: clock[0])
        policy = RoutePolicy(RouteClass.NORMAL_READ, capacity=2, refill_per_second=10)
        first = await bucket.consume("client", policy)
        second = await bucket.consume("client", policy)
        denied = await bucket.consume("client", policy)
        concurrent_results = await asyncio.gather(
            *(bucket.consume("concurrent", policy) for _ in range(4))
        )
        await redis.delete(f"{key}:refill", f"{key}:other", f"{key}:concurrent")
        refill_policy = RoutePolicy(RouteClass.NORMAL_READ, capacity=1, refill_per_second=2)
        refill_first = await bucket.consume("refill", refill_policy)
        clock[0] += 0.6
        refill_second = await bucket.consume("refill", refill_policy)
        other_class = await bucket.consume("other", RoutePolicy(RouteClass.OPS, 1, 1))
        await redis.set(f"{key}:corrupt", "invalid")
        with pytest.raises(RateLimitUnavailable):
            await bucket.consume("corrupt", policy)
        assert first.allowed and second.allowed and second.delay_seconds > 0 and not denied.allowed
        assert denied.retry_after >= 1
        assert sum(result.allowed for result in concurrent_results) == 2
        assert refill_first.allowed and refill_second.allowed
        assert other_class.allowed
    finally:
        await redis.delete(
            f"{key}:client",
            f"{key}:concurrent",
            f"{key}:refill",
            f"{key}:other",
            f"{key}:corrupt",
        )
        await redis.aclose()
