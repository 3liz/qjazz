#
# Test callback handlers
#

import socket

from ipaddress import ip_address
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from qjazz_processes.callbacks import accesscontrol
from qjazz_processes.callbacks.accesscontrol import AccessControlConfig
from qjazz_processes.callbacks.callbacks import Callbacks, HandlerConfig
from qjazz_processes.callbacks.handlers.http import (
    HttpCallback,
    HttpCallbackConfig,
)
from qjazz_processes.callbacks.handlers.mailto import get_recipients
from qjazz_processes.worker.mixins.callbacks import on_task_postrun

if TYPE_CHECKING:
    from qjazz_processes.worker.models import JobMeta


def test_callback_acl_allow():
    """Allow by default"""
    conf = AccessControlConfig(
        allow=(
            "192.168.0.8",
            ".foo.com",
        ),
        deny=(
            "192.168.0.0/24",
            "212.180.10.0",
        ),
        order="Allow",
    )

    assert not conf.check_ip(ip_address("192.168.0.2"))
    assert not conf.check_ip(ip_address("212.180.10.0"))
    assert conf.check_ip(ip_address("212.180.10.0"), "bar.foo.com")
    assert conf.check_ip(ip_address("192.168.0.8"))
    assert conf.check_ip(ip_address("172.10.0.1"))

    assert conf.check_hostname("projects.3liz.org")


def test_callback_acl_deny():
    """Deny by default"""
    conf = AccessControlConfig(
        allow=(
            "*.foo.com",
            "192.168.0.0/24",
            "212.180.10.0",
        ),
        deny=("192.168.0.8",),
        order="Deny",
    )

    assert conf.check_ip(ip_address("192.168.0.2"))
    assert conf.check_ip(ip_address("212.180.10.0"))
    assert conf.check_ip(ip_address("212.180.10.1"), "bar.foo.com")
    assert not conf.check_ip(ip_address("192.168.0.8"))
    assert not conf.check_ip(ip_address("172.10.0.1"))

    assert not conf.check_hostname("projects.3liz.org")


def test_callback_acl_ipv6_allow():
    """IPv6 addresses and networks with 'Allow' order"""
    conf = AccessControlConfig(
        allow=("fd00::8",),
        deny=(
            "::1",
            "fd00::/64",
        ),
        order="Allow",
    )

    assert not conf.check_ip(ip_address("::1"))
    assert not conf.check_ip(ip_address("fd00::2"))
    assert conf.check_ip(ip_address("fd00::8"))
    assert conf.check_ip(ip_address("2001:db8::1"))

    # Host from callback url
    assert not conf.check_hostname(urlsplit("http://[::1]:8080/callback").hostname)
    assert conf.check_hostname(urlsplit("http://[fd00::8]/callback").hostname)


def test_callback_acl_ipv6_deny():
    """IPv6 addresses and networks with 'Deny' order"""
    conf = AccessControlConfig(
        allow=(
            "2001:db8::1",
            "fd00::/64",
        ),
        deny=("fd00::8",),
        order="Deny",
    )

    assert conf.check_ip(ip_address("2001:db8::1"))
    assert conf.check_ip(ip_address("fd00::2"))
    assert not conf.check_ip(ip_address("fd00::8"))
    assert not conf.check_ip(ip_address("2001:db8::2"))

    assert conf.check_hostname(urlsplit("http://[2001:db8::1]/callback").hostname)
    assert not conf.check_hostname(urlsplit("http://[::1]/callback").hostname)


# Fake DNS resolution
HOSTS = {
    "public.foo.com": ("212.180.10.1",),
    "mixed.foo.com": ("212.180.10.1", "127.0.0.1"),
    "mixed6.foo.com": ("212.180.10.1", "::1"),
    "local.bar.com": ("127.0.0.1",),
}


def _getaddrinfo(host, port, *args, **kwargs):
    if host not in HOSTS:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return [
        (
            socket.AF_INET6 if ":" in ip else socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (ip, 80),
        )
        for ip in HOSTS[host]
    ]


@pytest.fixture()
def fake_dns(monkeypatch):
    monkeypatch.setattr(accesscontrol, "getaddrinfo", _getaddrinfo)


def test_callback_acl_hostname_all_addresses(fake_dns):
    """All resolved addresses must be allowed"""
    conf = AccessControlConfig(
        deny=(
            "127.0.0.0/8",
            "::1",
        ),
        order="Allow",
    )

    assert conf.check_hostname("public.foo.com")
    assert not conf.check_hostname("local.bar.com")
    # One denied address is enough to reject the host
    assert not conf.check_hostname("mixed.foo.com")
    assert not conf.check_hostname("mixed6.foo.com")


def test_callback_acl_hostname_filter(fake_dns):
    """Hostname filters apply to all resolved addresses"""
    conf = AccessControlConfig(
        allow=(".foo.com",),
        order="Deny",
    )

    assert conf.check_hostname("mixed.foo.com")
    assert not conf.check_hostname("local.bar.com")


def test_callback_acl_unresolved_hostname(fake_dns):
    """Unresolved hosts are not allowed"""
    conf = AccessControlConfig(order="Allow")

    assert conf.check_hostname("public.foo.com")
    assert not conf.check_hostname("unknown.foo.com")


def test_callback_mailto_recipients_acl(fake_dns):
    """Unauthorized or unresolved recipients are skipped"""
    conf = AccessControlConfig(deny=("127.0.0.0/8",), order="Allow")

    url = urlsplit("mailto:john@public.foo.com?cc=jane@local.bar.com&cc=bob@unknown.foo.com")
    params = parse_qs(url.query)

    assert list(get_recipients("to", url, params, conf)) == ["john@public.foo.com"]
    assert list(get_recipients("cc", url, params, conf)) == []


def test_callback_http_request(httpserver):
    handler = HttpCallback(("http",), HttpCallbackConfig())

    results = {
        "foo": "bar",
        "baz": 1,
    }

    job_id = "12345678"

    httpserver.expect_request(
        "/callback",
        method="POST",
        json=results,
        query_string={"job_id": job_id},
    ).respond_with_data("OK")

    url = httpserver.url_for("/callback")
    url = f"{url}?job_id={{job_id}}"
    print("\n::test_callback_http_request::url", url)

    resp = handler.send_request(urlsplit(url), job_id, data=results)
    assert resp.status_code == 200


class RecordCallbacks:
    def __init__(self):
        self.calls: list[tuple] = []

    def on_success(self, url, job_id, meta, results):
        self.calls.append(("success", url, job_id))

    def on_failure(self, url, job_id, meta):
        self.calls.append(("failure", url, job_id))


def _postrun(kwargs: dict, state: str) -> list[tuple]:
    callbacks = RecordCallbacks()
    task = SimpleNamespace(app=SimpleNamespace(processes_callbacks=callbacks))
    on_task_postrun(
        sender=None,
        task_id="job_01",
        task=task,  # type: ignore [arg-type]
        args=(),
        kwargs=kwargs,
        retval={},
        state=state,
    )
    return callbacks.calls


def test_callback_postrun_without_request():
    """Task failed before starting (i.e dismissed task): no request, no callback"""
    kwargs = {"__meta__": {}, "__run_config__": {}}
    assert _postrun(kwargs, "FAILURE") == []


def test_callback_postrun_failure():
    request = {"subscriber": {"failedUri": "https://foo.com/failed"}}
    calls = _postrun({"__meta__": {}, "request": request}, "FAILURE")
    assert calls == [("failure", "https://foo.com/failed", "job_01")]


def test_callback_postrun_no_subscriber():
    assert _postrun({"__meta__": {}, "request": {}}, "SUCCESS") == []


def test_callback_test_handler(monkeypatch):
    """The test handler accepts the arguments passed by 'Callbacks'"""
    from qjazz_processes.callbacks import callbacks

    errors: list = []
    monkeypatch.setattr(callbacks.logger, "error", lambda *args: errors.append(args))

    cb = Callbacks({"test": HandlerConfig(handler="qjazz_processes.callbacks.Test")})

    meta = cast(
        "JobMeta",
        {
            "created": "2026-10-31T00:00:00Z",
            "realm": None,
            "service": "test",
            "process_id": "processes_test:testsimplevalue",
            "expires": 900,
            "tag": None,
        },
    )

    cb.on_success("test://ok", "job_01", meta, {"OUTPUT": "1 x"})
    cb.on_failure("test://failed", "job_01", meta)
    cb.in_progress("test://progress", "job_01", meta)

    # Handler errors are swallowed and logged by 'Callbacks'
    assert errors == []
