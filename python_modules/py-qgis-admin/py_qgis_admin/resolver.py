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

from pathlib import Path
from pydantic import (
    Field,
)

import dns.asyncresolver

from py_qgis_contrib.core import logger  # noqa
from py_qgis_contrib.core.config import (
    Config,
    SSLConfig,
)

from .client import ClientConfig


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
    port: int = Field(title="Service port")
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = False
    ssl_files: Optional[SSLConfig] = None

    def resolver_id(self) -> str:
        return f"dns:{self.host}"


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

#
# Unix socket resolver
#


class SocketResolverConfig(Config):
    type: Literal['socket']
    path: Path = Field(title="Socket path")

    def resolver_id(self) -> str:
        return f"unix:{self.path}"


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
        return (ClientConfig(server_address=self.name),)

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
