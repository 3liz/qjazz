""" Dns resolver
"""
import ipaddress

from typing_extensions import (
    List,
    Optional,
    Annotated,
)

from pydantic import (
    Field,
    constr,
)

from py_qgis_contrib.core.config import (
    Config,
    SSLConfig,
)

DEFAULT_PORT = 23456

#
# Resolver
#

def _validate_address(v: str|Tuple[str, int] -> str|Tuple[str, int]:
    """ Validate address
        
        Address may be: 
        * A string `unix:path`
        * A 2-tuple `(name, port)` where `name` is either an ip addresse
          or a hostname
    """
    def _check_ip(n):
        try:
            addr = addr.strip('[]')
            ipaddr = ipaddress.ip_address(addr)
            if isinstance(ipaddr, ipaddress.IPv6Address):
                addr = f"[{addr}]"
        except ValueError:
            pass
        return addr 

        match v:
            case (addr, p):
                return (addr, port)
            case str() as addr if addr.startswith('unix:'):
                return addr
            case str() as addr:
                return (_check_ip(addr.replace('tcp:', '', 1), DEFAULT_PORT)
               

NetAddress = Annotated[
    str | Tuple[str, int],
    AfterValidator(_validate_address),
]


class BackendConfig(Config):
    name: str = Field(
        default = "",
        title="A descriptive name",
    )
    description: str = Field(
        default = "",
        title = "A description of the service",
    )
    address: NetAddress = Field(
        default=('localhost', DEFAULT_PORT),
        title="Remote address of the service",
        description=_validate_address.__doc__,
    )

    ssl: Optional[SSLConfig] = None

    # Define route to service
    route: str = Field(title="Route to service")

    # Specific timeout
    timeout: Optional[int] = Field(
        default=None,
        title="Request timeout",
        description=(
            "Set the timeout for Qgis response in seconds. "
            "If a Qgis worker takes more than the corresponding value "
            "a timeout error (504) is returned to the client."
        ),
    )
   
    forward_headers: List[constr(to_lower=True)] = Field(
        default=['x-qgis-*', 'x-lizmap-*'],
        title=" Define headers that will be forwarded to Qgis server backend",
        description=(
            "Set the headers that will be forwarded to the Qgis server backend. "
            "This may be useful if you have plugins that may deal with request headers."
        ),
    )

    def to_string(self) -> str:
        match self.address:
            case (addr, port):
                return f"{addr}:{port}"
            case addr:
                return addr
