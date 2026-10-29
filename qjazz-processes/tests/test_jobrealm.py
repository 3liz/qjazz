import pytest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from qjazz_processes.server.jobrealm import JOB_REALM_HEADER, JobRealmConfig


def _request(realm: str | None = None) -> web.Request:
    headers = {JOB_REALM_HEADER: realm} if realm is not None else {}
    return make_mocked_request("DELETE", "/jobs/job_01", headers=headers)


@pytest.fixture()
def conf() -> JobRealmConfig:
    return JobRealmConfig(enabled=True, admin_tokens=("admin",))


def test_jobrealm_disabled():
    conf = JobRealmConfig(enabled=False)
    assert conf.job_realm(_request()) is None
    assert conf.job_realm(_request("*")) is None


def test_jobrealm_valid(conf: JobRealmConfig):
    assert conf.job_realm(_request("realm_owner-01")) == "realm_owner-01"


def test_jobrealm_admin(conf: JobRealmConfig):
    # Admin tokens are catch all
    assert conf.job_realm(_request("admin")) is None


@pytest.mark.parametrize(
    "realm",
    [
        "",
        "*",
        "realm_owner*",
        "[a-z]*",
        "realm::owner",
        "short",
    ],
)
def test_jobrealm_invalid(conf: JobRealmConfig, realm: str):
    # Invalid realms must not be used as registry key patterns
    with pytest.raises(web.HTTPUnauthorized):
        conf.job_realm(_request(realm))
