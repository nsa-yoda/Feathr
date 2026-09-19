from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.rate_limit.identity import normalize_client_identity
from event_platform.rate_limit.local_bucket import LocalTokenBucket
from event_platform.rate_limit.models import RouteClass, RoutePolicy, consume_tokens
from event_platform.rate_limit.service import classify_route

pytestmark = pytest.mark.unit


def policy() -> RoutePolicy:
    return RoutePolicy(RouteClass.NORMAL_READ, capacity=2, refill_per_second=1)


def test_token_math_allows_denies_and_refills_deterministically() -> None:
    remaining, updated, allowed, retry, _ = consume_tokens(
        tokens=2, last_refill=0, now=0, policy=policy()
    )
    assert (remaining, updated, allowed, retry) == (1, 0, True, 0)
    remaining, _, allowed, retry, _ = consume_tokens(
        tokens=0, last_refill=0, now=0, policy=policy()
    )
    assert (remaining, allowed, retry) == (0, False, 1)
    remaining, _, allowed, _, _ = consume_tokens(tokens=0, last_refill=0, now=2, policy=policy())
    assert (remaining, allowed) == (1, True)


def test_route_classification_uses_templates_and_exempts_health() -> None:
    assert classify_route(method="POST", path="/events") == RouteClass.INGESTION
    assert classify_route(method="GET", path="/query") == RouteClass.NORMAL_READ
    assert classify_route(method="GET", path="/search") == RouteClass.EXPENSIVE_READ
    assert classify_route(method="GET", path="/ops/status") == RouteClass.OPS
    assert classify_route(method="GET", path="/health/live") is None


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
    bucket = LocalTokenBucket(max_entries=2, clock=lambda: clock[0], wall_clock=lambda: 100.0)
    await bucket.consume("one", policy())
    await bucket.consume("two", policy())
    await bucket.consume("three", policy())
    assert bucket.size == 2


@pytest.mark.asyncio
async def test_local_bucket_removes_idle_entries() -> None:
    clock = [0.0]
    bucket = LocalTokenBucket(
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


def test_health_is_exempt_from_rate_limiting() -> None:
    settings = ServiceSettings(env="test", rate_limit_normal_capacity=1)
    with TestClient(create_app(settings)) as client:
        responses = [client.get("/health/live") for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert all("RateLimit-Limit" not in response.headers for response in responses)
