""" Dns resolver
"""
from ipaddress import IPv4Address, IPv6Address
from typing import (
    Annotated,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import dns.asyncresolver

from dns.resolver import NoNameservers
from pydantic import Field, IPvAnyAddress, TypeAdapter

from qjazz_contrib.core import logger  # noqa
from qjazz_contrib.core.config import (
    ConfigBase,
    SSLConfig,
)

from .backend import BackendConfig

DEFAULT_PORT = 23456


ResolverAddress = Union[IPvAnyAddress, str]


ResolverLabel = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z][0-9a-zA-Z._]*$",
        title="Unique label",
        description=(
            "Unique resolver label. "
            "The label must be compatible with an url path component."
        ),
    ),
]


#
# Resolver config
#


class Resolver(ConfigBase):
    """
    Resolver configuration

    Resolver for DNS resolution that may resolve
    to multiple ips.
    """
    label: ResolverLabel
    address: Tuple[ResolverAddress, int] = Field(
        default=(IPv6Address("::1"), DEFAULT_PORT),
        title="RPC address",
    )
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = Field(default=False, title="Use ssl connection")
    ssl: SSLConfig = Field(default=SSLConfig(), title="SSL certificats")

    title: str = ""
    description: Optional[str] = None

    def resolver_address(self) -> str:
        return f"{self.address[0]}:{self.address[1]}"

    @property
    async def backends(self) -> Sequence[BackendConfig]:
        match self.address[0]:
            case IPv6Address() | IPv4Address():
                return (
                     BackendConfig(
                        server_address=(self.address[0], self.address[1]),
                        use_ssl=self.use_ssl,
                        ssl=self.ssl,
                    ),
                )
            case str(host):
                if self.ipv6:
                    rdtype = "AAAA"
                else:
                    rdtype = "A"
                try:
                    addresses = await dns.asyncresolver.resolve(host, rdtype)
                    IPAddressTA: TypeAdapter = TypeAdapter(IPvAnyAddress)
                    return tuple(
                        BackendConfig(
                            server_address=(
                                IPAddressTA.validate_python(addr),
                                self.address[1],
                            ),
                            use_ssl=self.use_ssl,
                            ssl=self.ssl,
                        )
                        for addr in addresses
                    )
                except NoNameservers:
                    logger.warning("No servers found at '%s' ", host)

        return ()


class ResolverConfig(ConfigBase):
    resolvers: List[Resolver] = Field(
        default=[],
        title="List of Rpc backends",
    )
