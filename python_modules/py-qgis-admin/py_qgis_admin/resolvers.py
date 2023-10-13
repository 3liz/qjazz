""" Dns resolver
"""
from abc import ABC, abstractmethod
from typing_extensions import (
    List,
    Optional,
    Sequence,
    Generator,
    Self,
    Union,
    Annotated,
    Literal,
)

from pydantic import (
    Field,
)

import dns.asyncresolver

from py_qgis_contrib.core import logger  # noqa
from py_qgis_contrib.core.config import (
    Config,
    SSLConfig,
    NetInterface,
)

from .client import ClientConfig


DEFAULT_PORT = 23456


class Resolver(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """
        """
        ...

    @property
    @abstractmethod
    async def configs(self) -> Sequence[ClientConfig]:
        """ Return a sequence of client configuration
        """
        ...

    @classmethod
    def get_resolvers(cls, config: Config) -> Generator[Self, None, None]:
        yield cls(config)


#
# DNS resolver
#

class DNSResolverConfig(Config):
    type: Literal['dns']
    host: str = Field(title="Host name")
    port: int = Field(title="Service port", default=DEFAULT_PORT)
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = False
    ssl_files: Optional[SSLConfig] = None

    def resolver_id(self) -> str:
        return f"{self.host}:{self.port}"


class DNSResolver(Resolver):
    """ DNS resolver from host name
    """

    def __init__(self, config: DNSResolverConfig):
        self._config = config

    @property
    def name(self) -> str:
        return self._config.resolver_id()

    @property
    async def configs(self) -> Sequence[ClientConfig]:
        if self._config.ipv6:
            rdtype = "AAAA"
        else:
            rdtype = "A"
        addresses = await dns.asyncresolver.resolve(self._config.host, rdtype)
        return (
            ClientConfig(
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
        return cls(DNSResolverConfig(host=host, port=port, type="dns"))

#
# Unix socket resolver
#


class SocketResolverConfig(Config):
    type: Literal['socket']
    address: NetInterface
    use_ssl: bool = False
    ssl_files: Optional[SSLConfig] = None

    def resolver_id(self) -> str:
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
    def name(self) -> str:
        return self._config.resolver_id()

    @property
    async def configs(self) -> Sequence[ClientConfig]:
        # Return a 1-tuple
        return (
            ClientConfig(
                server_address=self._config.address,
                use_ssl=self._config.use_ssl,
                ssl_files=self._config.ssl_files,
            ),
        )

    @classmethod
    def from_string(cls, name: str) -> Self:
        if not name.startswith('unix:'):
            addr, *rest = name.rsplit(':', 1)
            port = int(rest[0]) if rest else DEFAULT_PORT
            address = (addr, port)
        else:
            address = name
        return cls(SocketResolverConfig(address=address, type="socket"))


#
# Aggregate configuration for resolvers
#


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
    def from_string(name: str) -> Resolver:
        # Build a resolver directly from string
        match name:
            case n if n.startswith('unix:'):
                return SocketResolver.from_string(name)
            case n if n.startswith('tcp://'):
                return SocketResolver.from_string(name.removeprefix('tcp://'))
            case other:
                return DNSResolver.from_string(other)
