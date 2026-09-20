import pytest

from event_platform.core.composition import ApplicationServices, build_application_services
from event_platform.observability.health import HealthRegistry
from event_platform.observability.metrics import MetricsRegistry
from event_platform.queue import InProcessQueue

pytestmark = pytest.mark.unit


def test_application_services_container_declares_owned_and_optional_dependencies() -> None:
    services = build_application_services(
        queue=InProcessQueue(capacity=1),
        metrics=MetricsRegistry(),
        health=HealthRegistry(),
    )
    assert isinstance(services, ApplicationServices)
    assert services.event_store is None
    assert services.search_service is None
