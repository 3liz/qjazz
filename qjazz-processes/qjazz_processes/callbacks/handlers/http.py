#
# Http callback
#
from importlib.metadata import version
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
)
from socket import getaddrinfo
from typing import (
    Annotated,
    Literal,
    Optional,
    Sequence,
    assert_never,
)

import requests

from pydantic import (
    AfterValidator,
    FilePath,
    IPvAnyAddress,
    IPvAnyNetwork,
    PositiveInt,
    TypeAdapter,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.config import ConfigBase
from qjazz_contrib.core.models import Field, Option

from ...schemas import JobResults
from ..callbacks import Url

IPValidator: TypeAdapter = TypeAdapter(IPvAnyAddress)
HostValidator: TypeAdapter = TypeAdapter(IPvAnyAddress | str)


def _validate_filter(v):
    if isinstance(v, str) and v.startswith("*."):
        v = v.removeprefix("*")
    return v


HostFilterType = Annotated[
    IPvAnyAddress | IPvAnyNetwork | str,
    AfterValidator(_validate_filter),
]


class HttpCallbackConfig(ConfigBase):
    ca_cert: Option[FilePath] = Field(
        title="Path to CA file",
    )
    order: Literal["Allow", "Deny"] = Field(
        default="Allow",
        title="Authorization order",
        description="""
        Set the order of evaluation of allow and deny directives:
        - Allow: allow by default  except thoses in deny then
          put back those in deny with the allow directive.
        - Deny: deny by default  except thoses in allow then deny
          those in allow with the deny directive.
        """,
    )
    allow: Sequence[HostFilterType] = Field(
        default=[],
        title="Allowed addresses",
        description="""
        List of allowed hosts. An host may be a IP addresse at IP range
        in CIDR format or a FQDN or FQDN suffix starting with a dot (and
        an optional '*').
        """,
        examples=[
            """
            allow = [
                "foo.bar.com",
                "*.mydomain.com",
                "192.168.0.0/24",
                "192.168.1.2",
            ]
            """,
        ],
    )
    deny: Sequence[HostFilterType] = Field(
        default=[],
        title="Forbidden addresses",
        description="List of forbidden hosts in the same format as for 'allow' list.",
    )
    user_agent: str = Field(
        default=f"Qjazz processes v{version('qjazz_processes')}",
        title="User agent",
    )
    timeout: PositiveInt = Field(
        default=5,
        title="Request timeout",
        description="""
        The request timeout value for both connect and read timeout.
        """,
    )

    def allow_ip(self, ip: IPv4Address | IPv6Address, hostname: Optional[str]) -> bool:
        return any(match_ip(ip, allow_ip, hostname) for allow_ip in self.allow)

    def deny_ip(self, ip: IPv4Address | IPv6Address, hostname: Optional[str]) -> bool:
        return any(match_ip(ip, deny_ip, hostname) for deny_ip in self.deny)

    def check_ip(self, ip: IPv4Address | IPv6Address, hostname: Optional[str] = None) -> bool:
        # See description of 'order' about the logic
        if self.order == "Allow":
            return not self.deny_ip(ip, hostname) or self.allow_ip(ip, hostname)
        else:
            return self.allow_ip(ip, hostname) and not self.deny_ip(ip, hostname)

    def check_url(self, url: Url) -> bool:
        assert_precondition(url.scheme in ("http", "https"))

        host = HostValidator.validate_python(url.hostname)
        match host:
            case str():
                for _, _, _, _, addr in getaddrinfo(host, url.port or url.scheme):
                    if self.check_ip(IPValidator.validate_python(addr[0]), url.hostname):
                        return True
            case IPv4Address() | IPv6Address():
                return self.check_ip(host)
            case unreachable:
                assert_never(unreachable)

        return False


class HttpCallback:
    Config = HttpCallbackConfig

    def __init__(self, scheme: str, conf: HttpCallbackConfig):
        if scheme not in ("http", "https"):
            raise ValueError("HTTP callback: unsupported scheme '%s', 'http' or 'https' expected")

        self._conf = conf

    #
    # Callback protocol implementation
    #

    def on_success(self, url: Url, job_id: str, results: JobResults):
        self.send_request(url, job_id, results)

    def on_failure(self, url: Url, job_id: str):
        self.send_request(url, job_id)

    def in_progress(self, url: Url, job_id: str):
        self.send_request(url, job_id)

    #

    def send_request(
        self,
        url: Url,
        job_id: str,
        data: Optional[JobResults] = None,
    ) -> Optional[requests.Response]:
        if not self._conf.check_url(url):
            logger.error("Host not allowed in HTTP callback: %s", url.hostname)
            return None

        headers = {
            "x-job-id": job_id,
            "user-agent": self._conf.user_agent,
        }

        urlstr = url.geturl().format(job_id=job_id)

        kwargs: dict = {}
        if self._conf.ca_cert:
            kwargs.update(verify=str(self._conf.ca_cert))

        # Execute POST
        logger.debug("Sending HTTP callback to %s", urlstr)
        resp = requests.post(
            urlstr,
            json=data,
            headers=headers,
            timeout=self._conf.timeout,
            **kwargs,
        )
        if resp.status_code > 299:
            logger.error(
                "Callback request returned code %s: %s",
                resp.status_code,
                resp.text,
            )

        return resp


# Convenience functions


def match_ip(
    ip: IPvAnyAddress,
    test_ip: HostFilterType,
    hostname: Optional[str],
) -> bool:
    match test_ip:
        case IPv4Address() | IPv4Address():
            return ip == test_ip
        case IPv4Network() | IPv6Network():
            return ip in test_ip
        case str() if hostname:
            if test_ip.startswith("."):
                return hostname.endswith(test_ip)
            else:
                return test_ip == hostname
    return False  # Makes Mypy happy


def dump_toml_schema() -> None:
    from ..doc import dump_callback_config_schema

    dump_callback_config_schema(
        "qjazz_processes.callbacks.HttpCallback",
        HttpCallbackConfig,
    )

