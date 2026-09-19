from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.rate_limit import RateLimitUnavailable, RouteClass, RoutePolicy
from event_platform.rate_limit.local_bucket import LocalLeakyBucket
from event_platform.rate_limit.redis_bucket import RedisLeakyBucket
from event_platform.rate_limit.service import RateLimiter

pytestmark = pytest.mark.failure


class BrokenRedis:
    async def eval(self, *args: object) -> object:
        del args
        raise ConnectionError("secret redis endpoint")


@pytest.mark.asyncio
async def test_redis_failure_uses_local_fallback_without_raw_error() -> None:
    policies = {
        route_class: RoutePolicy(route_class, 1, 1)
        for route_class in RouteClass
        if route_class is not RouteClass.EXEMPT
    }
    limiter = RateLimiter(
        policies=policies,
        local_bucket=LocalLeakyBucket(max_entries=4),
        redis_bucket=RedisLeakyBucket(BrokenRedis()),  # type: ignore[arg-type]
    )
    scope = {"client": ("127.0.0.1", 1), "headers": []}
    decision = await limiter.check(scope, method="GET", path="/query")
    assert decision is not None and decision.backend == "local"


def test_redis_failure_keeps_safe_http_contract() -> None:
    settings = ServiceSettings(
        env="test", rate_limit_normal_capacity=1, rate_limit_normal_refill=0.1
    )
    with TestClient(create_app(settings)) as client:
        client.get("/openapi.json")
        response = client.get("/openapi.json")
    assert response.status_code == 429
    assert "secret redis" not in response.text
    assert "redis" not in response.text.lower()


def test_http_fallback_uses_broken_redis_adapter() -> None:
    settings = ServiceSettings(
        env="test", rate_limit_normal_capacity=1, rate_limit_normal_refill=0.1
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.rate_limiter.redis_bucket = RedisLeakyBucket(BrokenRedis())  # type: ignore[arg-type]
        first = client.get("/openapi.json")
        second = client.get("/openapi.json")
    assert first.status_code == 200
    assert second.status_code == 429
    assert "secret redis" not in second.text


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ([1, 2], [0, 0, 0, 0, 0], [1, 999, 0, 0, 999_999_999]))
@pytest.mark.asyncio
async def test_malformed_redis_result_is_classified(result: object) -> None:
    class BadResult:
        async def eval(self, *args: object) -> object:
            del args
            return result

    bucket = RedisLeakyBucket(BadResult())  # type: ignore[arg-type]
    with pytest.raises(RateLimitUnavailable) as error:
        await bucket.consume("hashed", RoutePolicy(RouteClass.NORMAL_READ, 1, 1))
    assert error.value.operation == "decode"
