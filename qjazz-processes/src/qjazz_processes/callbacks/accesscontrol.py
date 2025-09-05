#
# Acces control
#

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

from pydantic import (
    AfterValidator,
    IPvAnyAddress,
    IPvAnyNetwork,
    TypeAdapter,
)
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field

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


class AccessControlConfig(ConfigBase):
    """Access control configuration"""

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

    def check_hostname(self, hostname: str) -> bool:
        host = HostValidator.validate_python(hostname)
        match host:
            case str():
                for _, _, _, _, addr in getaddrinfo(host, "http"):
                    if self.check_ip(IPValidator.validate_python(addr[0]), hostname):
                        return True
            case IPv4Address() | IPv6Address():
                return self.check_ip(host)
            case unreachable:
                assert_never(unreachable)

        return False


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
