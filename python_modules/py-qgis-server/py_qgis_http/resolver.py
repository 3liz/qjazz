""" Dns resolver
"""
import ipaddress

from pathlib import PurePosixPath

from pydantic import (
    AfterValidator,
    Field,
    PlainSerializer,
    PlainValidator,
    StringConstraints,
    WithJsonSchema,
)
from typing_extensions import Annotated, List, Optional, Tuple

from py_qgis_contrib.core.config import ConfigBase, SSLConfig

DEFAULT_PORT = 23456

#
# Resolver
#


def _validate_address(v: str | Tuple[str, int]) -> str | Tuple[str, int]:
    """ Validate address

        Address may be:
        * A string `unix:path`
        * A 2-tuple `(name, port)` where `name` is either an ip addresse
          or a hostname
    """
    def _check_ip(addr):
        try:
            addr = addr.strip('[]')
            ipaddr = ipaddress.ip_address(addr)
            if isinstance(ipaddr, ipaddress.IPv6Address):
                addr = f"[{addr}]"
        except ValueError:
            # Assume this is a hostname
            pass
        return addr

    match v:
        case (str(addr), int(port)):
            return (_check_ip(addr.removeprefix('tcp://')), port)
        case str() as addr if addr.startswith('unix:'):
            return addr
        case str() as addr:
            return (_check_ip(addr.removeprefix('tcp://')), DEFAULT_PORT)
        case _ as addr:
            raise ValueError(f"Unmanageable address: {addr}")


NetAddress = Annotated[
    str | Tuple[str, int],
    AfterValidator(_validate_address),
]


def _validate_route(r: str) -> PurePosixPath:
    """ Validate a path:
        * Path must be absolute (i.e start with '/')
    """
    if not isinstance(r, str):
        raise ValueError("Expecting string")
    if not r.startswith('/'):
        raise ValueError("Route must starts with a '/'")
    if r != '/':
        r = r.removesuffix('/')
    return PurePosixPath(r)


Route = Annotated[
    PurePosixPath,
    PlainValidator(_validate_route),
    PlainSerializer(lambda x: str(x), return_type=str),
    WithJsonSchema({'type': 'str'}),
]


class ApiEndpoint(ConfigBase):
    endpoint: str = Field(
        pattern=r"^[^\/]+",
        title="Api endpoint",
    )
    delegate_to: Optional[str] = Field(
        default=None,
        title="Api name to delegate to",
        description=(
            "Api delegation allow for using a baseurl different\n"
            "from the expected rootpath of qgis server api.\n"
            "For exemple, wfs3 request may be mapped to a completely different\n"
            "root path. "
        ),
    )
    name: str = Field(
        default="",
        title="Descriptive name",
    )
    description: str = Field(
        default="",
        title="Api description",
    )
    enable_html_delegate: bool = Field(
        default=False,
        title="Enable html in delegated endpoint",
        description=(
            "Enable fetching html resources in delegated endpoints.\n"
            "Enable this if the delegated api handle correctly html\n"
            "template resource resolution in Qgis server when using\n"
            "delegated api endpoint."
        ),
    )


class BackendConfig(ConfigBase):
    title: str = Field(
        default="",
        title="A descriptive title",
    )
    description: str = Field(
        default="",
        title="A description of the service",
    )
    address: NetAddress = Field(
        default=('localhost', DEFAULT_PORT),
        title="Remote address of the service",
        description=_validate_address.__doc__,
    )

    use_ssl: bool = False
    ssl: SSLConfig = SSLConfig()

    # Define route to service
    route: Route = Field(title="Route to service")

    # Specific timeout
    timeout: int = Field(
        default=20,
        title="Request timeout",
        description=(
            "Set the timeout for Qgis response in seconds.\n"
            "If a Qgis worker takes more than the corresponding value\n"
            "a timeout error (504) is returned to the client."
        ),
    )

    forward_headers: List[Annotated[str, StringConstraints(to_lower=True)]] = Field(
        default=['x-qgis-*', 'x-lizmap-*'],
        title="Forwarded headers",
        description=(
            "Set the headers that will be forwarded to the Qgis server backend.\n"
            "This may be useful if you have plugins that may deal with request headers."
        ),
    )

    api: List[ApiEndpoint] = Field(
        default=[],
        title="Api endpoints",
    )

    allow_direct_resolution: bool = Field(
        default=False,
        title="Allow direct path resolution",
        description=(
            "Allow remote worker to use direct project path resolution.\n"
            "WARNING: allowing this may be a security vulnerabilty.\n"
            "See worker configuration for details."
        ),
    )

    getfeature_limit: Optional[Annotated[int, Field(gt=0)]] = Field(
        default=None,
        title="WFS/GetFeature limit",
        description=(
            "Force setting a limit for WFS/GetFeature requests.\n"
            "By default Qgis does not set limits and that may cause\n"
            "issues with large collections."
        ),
    )

    def to_string(self) -> str:
        match self.address:
            case (addr, port):
                return f"{addr}:{port}"
            case _ as addr:
                return str(addr)
