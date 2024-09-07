""" Dns resolver
"""
from abc import abstractmethod

import dns.asyncresolver

from pydantic import Field
from typing_extensions import (
    Annotated,
    Iterator,
    List,
    Literal,
    Protocol,
    Self,
    Sequence,
    Type,
    Union,
    no_type_check,
)

from py_qgis_contrib.core import logger  # noqa
from py_qgis_contrib.core.config import (
    ConfigBase,
    NetInterface,
    SSLConfig,
)

from .backend import BackendConfig

DEFAULT_PORT = 23456


class Resolver(Protocol):

    @property
    @abstractmethod
    def label(self) -> str:
        """ Unique label for this resolver
            Will be used as pool identifier
        """
        ...

    @property
    @abstractmethod
    def address(self) -> str:
        """
        """
        ...

    @property
    @abstractmethod
    async def configs(self) -> Sequence[BackendConfig]:
        """ Return a sequence of client configuration
        """
        ...


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


class ResolverConfigProto(Protocol):

    @property
    def label(self) -> str:
        ...

    def get_resolver(self) -> Resolver:
        ...

#
# DNS resolver
#


class DNSResolverConfig(ConfigBase):
    """
    DNS resolver config

    Resolver for DNS resolution that may resolve
    to multiple ips.
    """
    label: ResolverLabel
    type: Literal['dns'] = Field(description="Must be set to 'dns'")
    host: str = Field(title="Host name")
    port: int = Field(title="Service port", default=DEFAULT_PORT)
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = Field(default=False, title="Use ssl connection")
    ssl: SSLConfig = Field(default=SSLConfig(), title="SSL certificats")

    def resolver_address(self) -> str:
        return f"{self.host}:{self.port}"

    def get_resolver(self) -> Resolver:
        return DNSResolver(self)


class DNSResolver:
    """ DNS resolver from host name
    """

    def __init__(self, config: DNSResolverConfig):
        self._config = config

    @property
    def label(self) -> str:
        return self._config.label

    @property
    def address(self) -> str:
        return self._config.resolver_address()

    @property
    async def configs(self) -> Sequence[BackendConfig]:
        if self._config.ipv6:
            rdtype = "AAAA"
        else:
            rdtype = "A"
        addresses = await dns.asyncresolver.resolve(self._config.host, rdtype)
        return tuple(
            BackendConfig(
                server_address=(str(addr), self._config.port),
                use_ssl=self._config.use_ssl,
                ssl=self._config.ssl,
            )
            for addr in addresses
        )

    @classmethod
    def from_string(cls: Type[Self], name: str) -> Self:
        host, *rest = name.rsplit(':', 1)
        port = int(rest[0]) if rest else DEFAULT_PORT
        return cls(DNSResolverConfig(host=host, port=port, type="dns", label=name))

#
# Socket resolver
#
# Unix socket or direct ip resolution
#


class SocketResolverConfig(ConfigBase):
    """Resolver for socket resolution"""
    label: ResolverLabel
    type: Literal['socket'] = Field(description="Must be set to 'socket'")
    address: NetInterface
    use_ssl: bool = False
    ssl: SSLConfig = Field(default=SSLConfig(), title="SSL certificats")

    @no_type_check
    def resolver_address(self) -> str:
        match self.address:
            case (addr, port):
                return f"{addr}:{port}"
            case socket:
                return socket

    def get_resolver(self) -> Resolver:
        return SocketResolver(self)


class SocketResolver(Resolver):
    """ DNS resolver from host name
    """

    def __init__(self, config: SocketResolverConfig):
        self._config = config

    @property
    def label(self) -> str:
        return self._config.label

    @property
    def address(self) -> str:
        return self._config.resolver_address()

    @property
    async def configs(self) -> Sequence[BackendConfig]:
        # Return a 1-tuple
        return (
            BackendConfig(
                server_address=self._config.address,
                use_ssl=self._config.use_ssl,
                ssl=self._config.ssl,
            ),
        )

    @classmethod
    def from_string(cls: Type[Self], address: str) -> Self:
        name = address
        if not address.startswith('unix:'):
            addr, *rest = address.rsplit(':', 1)
            port = int(rest[0]) if rest else DEFAULT_PORT
            address = (addr, port)  # type: ignore
        return cls(SocketResolverConfig(address=address, type="socket", label=name))


#
# Aggregate configuration for resolvers
#

ResolverConfigUnion = Annotated[
    Union[
        DNSResolverConfig,
        SocketResolverConfig,
    ],
    Field(discriminator='type'),
]


class ResolverConfig(ConfigBase):
    pools: List[ResolverConfigUnion] = Field(
        default=[],
        title="List of Qgis pool backends",
    )

    def get_resolvers(self) -> Iterator[Resolver]:
        for config in self.pools:
            yield config.get_resolver()

    @staticmethod
    def from_string(address: str) -> Resolver:
        # Build a resolver directly from string
        match address:
            case n if n.startswith('unix:'):
                return SocketResolver.from_string(address)
            case n if n.startswith('tcp://'):
                return SocketResolver.from_string(address.removeprefix('tcp://'))
            case _:
                return DNSResolver.from_string(address)
