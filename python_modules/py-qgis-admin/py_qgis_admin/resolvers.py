""" Dns resolver
"""
from abc import ABC, abstractmethod

import dns.asyncresolver

from pydantic import Field, TypeAdapter
from typing_extensions import (
    Annotated,
    Generator,
    List,
    Literal,
    Optional,
    Self,
    Sequence,
    Union,
)

from py_qgis_contrib.core import logger  # noqa
from py_qgis_contrib.core.config import (
    Config,
    NetInterface,
    SSLConfig,
    section,
)

from .backend import BackendConfig

DEFAULT_PORT = 23456


class Resolver(ABC):

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

    @classmethod
    def get_resolvers(cls, config: Config) -> Generator[Self, None, None]:
        """ Given a configuration, returns
            all resolvers available from it.

            This allow to define 'meta' resolvers that returns
            multiple sub-resolvers
        """
        yield cls(config)


class BaseResolverConfig(Config):
    label: str = Field(
        pattern=r"^[a-zA-Z][0-9a-zA-Z._]*$",
        title="Unique label",
        description=(
            "Unique resolver label. "
            "The label must be compatible with a url path component."
        )
    )

#
# DNS resolver
#


class DNSResolverConfig(BaseResolverConfig):
    type: Literal['dns']
    host: str = Field(title="Host name")
    port: int = Field(title="Service port", default=DEFAULT_PORT)
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = False
    ssl_files: Optional[SSLConfig] = None

    def resolver_address(self) -> str:
        return f"{self.host}:{self.port}"


class DNSResolver(Resolver):
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
        return (
            BackendConfig(
                server_address=(str(addr), self._config.port),
                use_ssl=self._config.use_ssl,
                ssl_files=self._config.ssl_files,
            )
            for addr in addresses
        )

    @classmethod
    def from_string(cls, name: str) -> Self:
        host, *rest = name.rsplit(':', 1)
        port = int(rest[0]) if rest else DEFAULT_PORT
        return cls(DNSResolverConfig(host=host, port=port, type="dns", label=name))

#
# Unix socket resolver
#


class SocketResolverConfig(BaseResolverConfig):
    type: Literal['socket']
    address: NetInterface
    use_ssl: bool = False
    ssl_files: Optional[SSLConfig] = None

    def resolver_address(self) -> str:
        match self.address:
            case (addr, port):
                return f"{addr}:{port}"
            case socket:
                return socket


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
                ssl_files=self._config.ssl_files,
            ),
        )

    @classmethod
    def from_string(cls, address: str) -> Self:
        if not address.startswith('unix:'):
            addr, *rest = address.rsplit(':', 1)
            port = int(rest[0]) if rest else DEFAULT_PORT
            address = (addr, port)
        return cls(SocketResolverConfig(address=address, type="socket"))


#
# Aggregate configuration for resolvers
#

RESOLVERS_SECTION = 'resolvers'

# Used for validating dynamic resolver configuration
ResolverConfigList = TypeAdapter(
    List[
        Union[
            DNSResolverConfig,
            SocketResolverConfig,
        ]
    ]
)


@section(RESOLVERS_SECTION)
class ResolverConfig(Config):
    pools: List[
        Annotated[
            Union[
                DNSResolverConfig,
                SocketResolverConfig,
            ],
            Field(discriminator='type')
        ]
    ] = Field(default=[])

    def get_resolvers(self) -> Generator[Resolver, None, None]:
        for config in self.pools:
            match config:
                case DNSResolverConfig():
                    yield from DNSResolver.get_resolvers(config)
                case SocketResolverConfig():
                    yield from SocketResolver.get_resolvers(config)

    @staticmethod
    def from_string(address: str) -> Resolver:
        # Build a resolver directly from string
        match address:
            case n if n.startswith('unix:'):
                return SocketResolver.from_string(address)
            case n if n.startswith('tcp://'):
                return SocketResolver.from_string(address.removeprefix('tcp://'))
            case other:
                return DNSResolver.from_string(other)
