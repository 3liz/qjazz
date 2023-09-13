""" Configuration common definitions
"""
import os
from ._service import Config
from pathlib import Path
from urllib.parse import urlsplit
from pydantic import (
    Field,
    AfterValidator,
    PlainValidator,
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
        if v[0] != "[::]":
            if not v[0]:
                v[0] = "[::]"
            else:
                # This raise a ValueError on invalide ip addresse
                ipaddress.ip_address(v[0])
    return v


NetInterface = Annotated[
    str | Tuple[str, int],
    AfterValidator(_validate_netinterface),
]


def _validate_address(v: str | Tuple[str, int]) -> str | Tuple[str, int]:
    if isinstance(v, str):
        uri = urlsplit(str)
        match uri.scheme:
            case "unix" | "":
                if not uri.path:
                    raise ValueError("Missing unix socket path")
                return f"unix:{os.path.abspath(uri.path)}"
            case "tcp":
                if not uri.hostname:
                    raise ValueError("Missing hostname")
                if not uri.port:
                    raise ValueError("Missing port")
                return (uri.hostname, uri.port)
            case _:
                raise ValueError("Invalid address")
    else:
        return v


Address = Annotated[
    str | Tuple[str, int],
    PlainValidator(_validate_address),
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
