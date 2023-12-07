""" Dns resolver
"""
from abc import ABC, abstractmethod

import dns.asyncresolver

from pydantic import ConfigDict, Field
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

    def get_resolvers(self):
        raise NotImplementedError("Subclass must implement 'get_resolvers'")

#
# DNS resolver
#


class DNSResolverConfig(BaseResolverConfig):
    (
        "Resolver for DNS resolution that may resolve\n"
        "to multiple ips."
    )
    type: Literal['dns'] = Field(description="Must be set to 'dns'")
    host: str = Field(title="Host name")
    port: int = Field(title="Service port", default=DEFAULT_PORT)
    ipv6: bool = Field(default=False, title="Check for ipv6")
    use_ssl: bool = Field(default=False, title="Use ssl connection")
    ssl: Optional[SSLConfig] = Field(default=None, title="SSL certificats")

    def resolver_address(self) -> str:
        return f"{self.host}:{self.port}"

    def get_resolvers(self) -> Generator[Resolver, None, None]:
        yield from DNSResolver.get_resolvers(self)


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
                ssl=self._config.ssl,
            )
            for addr in addresses
        )

    @classmethod
    def from_string(cls, name: str) -> Self:
        host, *rest = name.rsplit(':', 1)
        port = int(rest[0]) if rest else DEFAULT_PORT
        return cls(DNSResolverConfig(host=host, port=port, type="dns", label=name))

#
# Socket resolver
#
# Unix socket or direct ip resolution
#


class SocketResolverConfig(BaseResolverConfig):
    """Resolver for socket resolution"""
    type: Literal['socket'] = Field(description="Must be set to 'socket'")
    address: NetInterface
    use_ssl: bool = False
    ssl: Optional[SSLConfig] = Field(default=None, title="SSL certificats")

    def resolver_address(self) -> str:
        match self.address:
            case (addr, port):
                return f"{addr}:{port}"
            case socket:
                return socket

    def get_resolvers(self) -> Generator[Resolver, None, None]:
        yield from SocketResolver.get_resolvers(self)


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
    def from_string(cls, address: str) -> Self:
        if not address.startswith('unix:'):
            addr, *rest = address.rsplit(':', 1)
            port = int(rest[0]) if rest else DEFAULT_PORT
            address = (addr, port)
        return cls(SocketResolverConfig(address=address, type="socket"))


#
# Resolver's plugin extension
#
RESOLVER_ENTRYPOINTS = '3liz.org.map.admin.resolver'
RESOLVER_CONTRACTID = '@3liz.org/map/admin/resolver;1'


class PluginResolverConfig(BaseResolverConfig):
    (
        "Plugin resolver\n\n"
        "Load resolver from entrypoint extension"
    )
    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: Literal['plugin'] = Field(description="Must be set to 'plugin'")
    name: str = Field(title="Resolver name")

    options: dict = Field(title="Resolver configuration options")

    def get_resolvers(self) -> Generator[Resolver, None, None]:
        from py_qgis_contrib.core import componentmanager as cm
        cm.load_entrypoint(RESOLVER_ENTRYPOINTS, self.name)

        return cm.get_service(
            f"{RESOLVER_CONTRACTID}?name={self.name}"
        ).get_resolvers(self)


#
# Aggregate configuration for resolvers
#
RESOLVERS_SECTION = 'resolvers'

ResolverConfigAnnotated = Annotated[
    Union[
        DNSResolverConfig,
        SocketResolverConfig,
        PluginResolverConfig,
    ],
    Field(discriminator='type'),
]


@section(RESOLVERS_SECTION)
class ResolverConfig(Config):
    pools: List[ResolverConfigAnnotated] = Field(
        default=[],
        title="List of Qgis pool backends",
    )

    def get_resolvers(self) -> Generator[Resolver, None, None]:
        for config in self.pools:
            yield from config.get_resolvers()

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
