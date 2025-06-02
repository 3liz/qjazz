#
# Test callback handlers
#

from ipaddress import ip_address
from urllib.parse import urlsplit

from qjazz_processes.callbacks.handlers.http import (
    HttpCallback,
    HttpCallbackConfig,
)


def test_callback_http_allow():
    """Allow by default"""
    conf = HttpCallbackConfig(
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

    assert conf.check_url(urlsplit("http://projects.3liz.org"))


def test_callback_http_deny():
    """Deny by default"""
    conf = HttpCallbackConfig(
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

    assert not conf.check_url(urlsplit("http://projects.3liz.org"))


def test_callback_http_request(httpserver):
    handler = HttpCallback("http", HttpCallbackConfig())

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
