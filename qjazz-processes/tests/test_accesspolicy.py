#
# Test the default access policy
#
import json

from types import SimpleNamespace

import pytest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from qjazz_processes.server.policies.default import (
    DefaultAccessPolicy,
    DefaultAccessPolicyConfig,
)


@pytest.fixture()
def policy() -> DefaultAccessPolicy:
    policy = DefaultAccessPolicy(DefaultAccessPolicyConfig())
    # Single available service
    policy.executor = SimpleNamespace(  # type: ignore [assignment]
        known_service=lambda service: service == "test",
        num_services=1,
        services=[SimpleNamespace(service="test")],
    )
    return policy


def test_accesspolicy_service(policy: DefaultAccessPolicy):
    assert policy.get_service(make_mocked_request("GET", "/jobs/?service=test")) == "test"
    # Default to the available service
    assert policy.get_service(make_mocked_request("GET", "/jobs/")) == "test"


@pytest.mark.parametrize(
    "service",
    [
        "*",
        "t?st",
        "[a-z]*",
        "test::other",
        "Test",
        "my-service",
    ],
)
def test_accesspolicy_invalid_service(policy: DefaultAccessPolicy, service: str):
    """Service names are validated before being used in registry key patterns"""
    request = make_mocked_request("GET", "/jobs/", headers={}).clone(
        rel_url=f"/jobs/?service={service.replace('?', '%3F')}",
    )
    with pytest.raises(web.HTTPBadRequest) as err:
        policy.get_service(request)

    body = json.loads(err.value.text or "")
    assert body["details"] == {"service": service}
