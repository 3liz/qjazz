""" Configuration common definitions
"""
from ._service import Config
from pathlib import Path
from pydantic import (
    Field,
    AfterValidator,
)
from typing_extensions import Annotated, Tuple

__all__ = [
    'NetInterface',
    'SSLConfig',
]


def _validate_netinterface(v: Tuple[str, int]) -> Tuple[str, int]:
    import ipaddress
    # This raise a ValueError on invalide ip addresse
    ipaddress.ip_address(v[0])


NetInterface = Annotated[
    Tuple[str, int],
    AfterValidator(_validate_netinterface),
]


#
# SSL configuration
#

def _verify_path(p: str):
    if not Path(p).exists():
        raise ValueError(f"File '{p}' does not exist")
    return p


class SSLConfig(Config):
    tls_cert_file: Annotated[str, AfterValidator(_verify_path)] = Field(
        title="SSL/TLS key",
        description="Path to the SSL key file"
    )
    tls_key_file: Annotated[str, AfterValidator(_verify_path)] = Field(
        title="SSL/TLS Certificat",
        description="Path to the SSL certificat file",
    )
