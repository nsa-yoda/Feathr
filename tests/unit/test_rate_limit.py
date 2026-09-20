from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.rate_limit.identity import normalize_client_identity
from event_platform.rate_limit.local_bucket import LocalLeakyBucket
from event_platform.rate_limit.models import RouteClass, RoutePolicy, schedule_request
from event_platform.rate_limit.redis_bucket import RateLimitUnavailable, RedisLeakyBucket
from event_platform.rate_limit.service import RateLimiter, classify_route

pytestmark = pytest.mark.unit


def policy() -> RoutePolicy:
    return RoutePolicy(RouteClass.NORMAL_READ, capacity=2, refill_per_second=1)


def policies() -> dict[RouteClass, RoutePolicy]:
    return {
        route_class: RoutePolicy(route_class, capacity=2, refill_per_second=1)
        for route_class in (
            RouteClass.INGESTION,
            RouteClass.NORMAL_READ,
            RouteClass.EXPENSIVE_READ,
            RouteClass.OPS,
        )
    }


def fixed_local_bucket() -> LocalLeakyBucket:
    return LocalLeakyBucket(clock=lambda: 100.0, wall_clock=lambda: 1_000.0)


def test_leaky_bucket_math_queues_until_the_bounded_backlog_is_full() -> None:
    next_slot, allowed, remaining, delay, retry = schedule_request(
        next_slot=0, now=0, policy=policy()
    )
    assert (next_slot, allowed, remaining, delay, retry) == (1, True, 1, 0, 0)
    next_slot, allowed, remaining, delay, retry = schedule_request(
        next_slot=next_slot, now=0, policy=policy()
    )
    assert (next_slot, allowed, remaining, delay, retry) == (2, True, 0, 1, 0)
    unchanged, allowed, remaining, delay, retry = schedule_request(
        next_slot=next_slot, now=0, policy=policy()
    )
    assert (unchanged, allowed, remaining, delay, retry) == (2, False, 0, 0, 1)
    _, allowed, _, delay, _ = schedule_request(next_slot=next_slot, now=1, policy=policy())
    assert (allowed, delay) == (True, 1)


@pytest.mark.parametrize(
    ("capacity", "leak_rate", "maximum_delay"),
    ((1_000, 100.0, 0.02), (500, 50.0, 5.1)),
)
def test_ingestion_policy_admits_ui_500_request_window(
    capacity: int, leak_rate: float, maximum_delay: float
) -> None:
    ingestion = RoutePolicy(RouteClass.INGESTION, capacity, leak_rate)
    next_slot = 0.0
    delays: list[float] = []
    for index in range(500):
        now = index * (5.0 / 499)
        next_slot, allowed, _, delay, _ = schedule_request(
            next_slot=next_slot, now=now, policy=ingestion
        )
        assert allowed
        delays.append(delay)
    assert max(delays) <= maximum_delay


def test_route_classification_uses_templates_and_exempts_health() -> None:
    assert classify_route(method="POST", path="/events") == RouteClass.INGESTION
    assert classify_route(method="GET", path="/query") == RouteClass.NORMAL_READ
    assert classify_route(method="GET", path="/search") == RouteClass.EXPENSIVE_READ
    assert classify_route(method="GET", path="/events/search") == RouteClass.EXPENSIVE_READ
    assert classify_route(method="GET", path="/events/stats") == RouteClass.EXPENSIVE_READ
    assert classify_route(method="POST", path="/operations/search-rebuild") == RouteClass.OPS
    assert classify_route(method="GET", path="/ops/status") == RouteClass.OPS
    assert classify_route(method="GET", path="/health/live") is None


def test_rate_limiter_requires_a_complete_non_exempt_policy_registry() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        RateLimiter(
            policies={RouteClass.NORMAL_READ: policy()},
            local_bucket=fixed_local_bucket(),
        )
    invalid = policies()
    invalid[RouteClass.NORMAL_READ] = RoutePolicy(
        RouteClass.NORMAL_READ, capacity=2, refill_per_second=1, exempt=True
    )
    with pytest.raises(ValueError, match="does not match"):
        RateLimiter(policies=invalid, local_bucket=fixed_local_bucket())


@pytest.mark.asyncio
async def test_rate_limiter_falls_back_to_local_after_redis_unavailability() -> None:
    class UnavailableBucket:
        async def consume(self, _key: str, _policy: RoutePolicy) -> object:
            raise RateLimitUnavailable("eval")

    limiter = RateLimiter(
        policies=policies(),
        local_bucket=fixed_local_bucket(),
        redis_bucket=UnavailableBucket(),  # type: ignore[arg-type]
    )
    decision = await limiter.check({"client": ("127.0.0.1", 1234)}, method="GET", path="/events")
    assert decision is not None
    assert decision.backend == "local"


@pytest.mark.asyncio
async def test_redis_bucket_validates_script_result_and_maps_transport_failure() -> None:
    class EvalClient:
        def __init__(self, result: object) -> None:
            self.result = result

        async def eval(self, *_args: object) -> object:
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

    valid = RedisLeakyBucket(EvalClient([1, 1, 250, 0, 100_250]), clock=lambda: 100.0)  # type: ignore[arg-type]
    decision = await valid.consume("key", policy())
    assert decision.allowed is True
    assert decision.remaining == 1
    assert decision.backend == "redis"
    assert decision.delay_seconds == 0.25

    malformed = RedisLeakyBucket(EvalClient([1, "1", 0, 0, 100_000]), clock=lambda: 100.0)  # type: ignore[arg-type]
    with pytest.raises(RateLimitUnavailable, match="decode"):
        await malformed.consume("key", policy())

    unavailable = RedisLeakyBucket(EvalClient(TimeoutError()), clock=lambda: 100.0)  # type: ignore[arg-type]
    with pytest.raises(RateLimitUnavailable, match="eval"):
        await unavailable.consume("key", policy())


def test_identity_ignores_forwarding_by_default_and_accepts_valid_trusted_chain() -> None:
    scope: Mapping[str, object] = {
        "client": ("2001:0DB8::1", 1234),
        "headers": [(b"x-forwarded-for", b"198.51.100.5, 2001:db8::1")],
    }
    assert normalize_client_identity(scope) == "2001:db8::1"
    assert normalize_client_identity(scope, trusted_proxy_hops=1) == "198.51.100.5"
    malformed = {**scope, "headers": [(b"x-forwarded-for", b"198.51.100.5")]}
    assert normalize_client_identity(malformed, trusted_proxy_hops=1) == "2001:db8::1"
    for forwarded in (
        b"not-an-ip, 2001:db8::1",
        b"198.51.100.5,,2001:db8::1",
        b"198.51.100.5, 2001:db8::1, 203.0.113.4",
    ):
        malformed_chain = {**scope, "headers": [(b"x-forwarded-for", forwarded)]}
        assert normalize_client_identity(malformed_chain, trusted_proxy_hops=1) == "2001:db8::1"


@pytest.mark.asyncio
async def test_local_bucket_evicts_oldest_identity_at_bound() -> None:
    clock = [0.0]
    bucket = LocalLeakyBucket(max_entries=2, clock=lambda: clock[0], wall_clock=lambda: 100.0)
    await bucket.consume("one", policy())
    await bucket.consume("two", policy())
    await bucket.consume("three", policy())
    assert bucket.size == 2


@pytest.mark.asyncio
async def test_local_bucket_removes_idle_entries() -> None:
    clock = [0.0]
    bucket = LocalLeakyBucket(
        max_entries=4,
        idle_ttl_seconds=5,
        clock=lambda: clock[0],
        wall_clock=lambda: 100.0,
    )
    await bucket.consume("idle", policy())
    clock[0] = 6
    await bucket.consume("active", policy())
    assert bucket.size == 1


def test_rate_limit_middleware_returns_problem_and_headers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = ServiceSettings(
        env="test",
        rate_limit_normal_capacity=1,
        rate_limit_normal_refill=0.1,
    )
    caplog.set_level("INFO", logger="event_platform.rate_limit")
    with TestClient(create_app(settings)) as client:
        first = client.get("/openapi.json")
        second = client.get("/openapi.json")
    assert first.status_code == 200
    assert first.headers["RateLimit-Limit"] == "1"
    assert "RateLimit-Remaining" in first.headers
    assert second.status_code == 429
    assert second.headers["content-type"].startswith("application/problem+json")
    assert second.headers["Retry-After"] == "20"
    assert second.headers["RateLimit-Limit"] == "1"
    assert second.json()["error_code"] == "rate_limit_exceeded"
    assert "rate-limit" not in second.text
    rate_records = [
        record for record in caplog.records if record.name == "event_platform.rate_limit"
    ]
    events = {record.__dict__.get("event") for record in rate_records}
    assert "rate_limit.allow" in events
    assert "rate_limit.deny" in events
    assert all(record.__dict__.get("request_id") for record in rate_records)


def test_rate_limit_middleware_queues_before_rejecting_full_backlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("event_platform.api.middleware.rate_limit._wait_for_slot", record_delay)
    settings = ServiceSettings(
        env="test",
        rate_limit_normal_capacity=4,
        rate_limit_normal_refill=0.1,
    )
    with TestClient(create_app(settings)) as client:
        first = client.get("/openapi.json")
        queued = client.get("/openapi.json")
        overflow = client.get("/openapi.json")
    assert first.status_code == 200
    assert queued.status_code == 200
    assert queued.headers["X-RateLimit-Queued"] == "true"
    assert delays and delays[0] > 9
    assert overflow.status_code == 429
    assert overflow.json()["error_code"] == "rate_limit_exceeded"
    assert overflow.json()["detail"] == "The bounded request admission backlog is full."


def test_health_is_exempt_from_rate_limiting() -> None:
    settings = ServiceSettings(env="test", rate_limit_normal_capacity=1)
    with TestClient(create_app(settings)) as client:
        responses = [client.get("/health/live") for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert all("RateLimit-Limit" not in response.headers for response in responses)
