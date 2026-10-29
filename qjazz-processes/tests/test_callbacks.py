#
# Test callback handlers
#

from ipaddress import ip_address
from urllib.parse import urlsplit

from qjazz_processes.callbacks.accesscontrol import AccessControlConfig
from qjazz_processes.callbacks.handlers.http import (
    HttpCallback,
    HttpCallbackConfig,
)


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
