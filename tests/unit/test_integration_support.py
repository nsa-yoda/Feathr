from __future__ import annotations

import math

import pytest
from tests.integration.support import IntegrationNamespace, PollTimeout, new_namespace, poll_until

pytestmark = pytest.mark.unit


def test_namespace_is_validated_and_allocated() -> None:
    namespace = new_namespace()
    assert len(namespace.suffix) == 12
    with pytest.raises(ValueError):
        IntegrationNamespace("")
    with pytest.raises(ValueError):
        IntegrationNamespace("unsafe-name!")


@pytest.mark.asyncio
async def test_poll_until_rejects_nonfinite_bounds() -> None:
    async def never_ready() -> None:
        return None

    with pytest.raises(ValueError):
        await poll_until("bounded", never_ready, timeout_seconds=math.inf)
    with pytest.raises(ValueError):
        await poll_until("bounded", never_ready, interval_seconds=math.nan)


@pytest.mark.asyncio
async def test_poll_timeout_redacts_untrusted_observations_and_operation() -> None:
    async def never_ready() -> None:
        return None

    with pytest.raises(PollTimeout) as error:
        await poll_until(
            "safe operation",
            never_ready,
            timeout_seconds=0.001,
            observe=lambda _: "secret-password",
        )
    assert "safe operation" in str(error.value)
    assert "last_observation=str" in str(error.value)
    assert "secret" not in str(error.value)
