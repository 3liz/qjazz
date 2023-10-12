""" Configuration common definitions
"""
from ._service import Config
from pathlib import Path
from pydantic import (
    Field,
    AfterValidator,
)
from typing_extensions import (
    Annotated,
    Tuple,
    Optional,
)

__all__ = [
    'NetInterface',
    'SSLConfig',
]


def _validate_netinterface(v: str | Tuple[str, int]) -> str | Tuple[str, int]:
    if isinstance(v, str):
        if not v.startswith("unix:"):
            raise ValueError("Invalid socket address")
    else:
        import ipaddress
        addr = v[0].strip('[]')
        # This raise a ValueError on invalid ip address
        ipaddr = ipaddress.ip_address(addr)
        if isinstance(ipaddr, ipaddress.IPv6Address):
            return (f"[{addr}]", v[1])
    return v


NetInterface = Annotated[
    str | Tuple[str, int],
    AfterValidator(_validate_netinterface),
]


#
# SSL configuration
#

def _path_exists(p: Optional[str]):
    if p is not None and not Path(p).exists():
        raise ValueError(f"File '{p}' does not exist")
    return p


class SSLConfig(Config):
    ca: Annotated[Optional[str], AfterValidator(_path_exists)] = Field(
        default=None,
        title="CA file"
    )
    cert: Annotated[Optional[str], AfterValidator(_path_exists)] = Field(
        default=None,
        title="SSL/TLS key",
        description="Path to the SSL key file"
    )
    key: Annotated[Optional[str], AfterValidator(_path_exists)] = Field(
        default=None,
        title="SSL/TLS Certificat",
        description="Path to the SSL certificat file",
    )
