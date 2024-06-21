""" Configuration common definitions
"""
import ssl

from pydantic import AfterValidator, Field, FilePath
from typing_extensions import Annotated, Optional, Tuple

from ._service import Config

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

class SSLConfig(Config):
    cafile: Optional[FilePath] = Field(
        default=None,
        title="CA file",
    )
    certfile: Optional[FilePath] = Field(
        default=None,
        title="SSL/TLS  key",
        description="Path to the SSL key file",
    )
    keyfile: Optional[FilePath] = Field(
        default=None,
        title="SSL/TLS Certificat",
        description="Path to the SSL certificat file",
    )

    #
    # Convenient methods for creating ssl context
    #

    def create_ssl_context(self, purpose: ssl.Purpose) -> ssl.SSLContext:
        """ Used for validating server client side """
        ssl_context = ssl.create_default_context(
            purpose=purpose,
            cafile=self.cafile.as_posix() if self.cafile else None,
        )
        if self.certfile and self.keyfile:
            ssl_context.load_cert_chain(self.certfile.as_posix(), self.keyfile.as_posix())
        return ssl_context

    def create_ssl_client_context(self) -> ssl.SSLContext:
        """ Used client side """
        return self.create_ssl_context(ssl.Purpose.SERVER_AUTH)

    def create_ssl_server_context(self) -> ssl.SSLContext:
        """ Used server side """
        return self.create_ssl_context(ssl.Purpose.CLIENT_AUTH)
