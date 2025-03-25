"""Dns resolver"""

from pathlib import PurePosixPath
from typing import Annotated

from pydantic import (
    FilePath,
    PlainSerializer,
    PlainValidator,
    StringConstraints,
    WithJsonSchema,
)

from qjazz_contrib.core.config import ConfigBase
from qjazz_contrib.core.models import Field, Option

DEFAULT_PORT = 23456

#
# Resolver
#


def _validate_route(r: str) -> PurePosixPath:
    """Validate a path:
    * Path must be absolute (i.e start with '/')
    """
    if not isinstance(r, str):
        raise ValueError("Expecting string")
    if not r.startswith("/"):
        raise ValueError("Route must starts with a '/'")
    if r != "/":
        r = r.removesuffix("/")
    return PurePosixPath(r)


Route = Annotated[
    PurePosixPath,
    PlainValidator(_validate_route),
    PlainSerializer(lambda x: str(x), return_type=str),
    WithJsonSchema({"type": "str"}),
]


class ApiEndpoint(ConfigBase):
    endpoint: str = Field(
        pattern=r"^[^\/]+",
        title="Api endpoint",
    )
    delegate_to: Option[str] = Field(
        title="Api name to delegate to",
        description="""
          Api delegation allow for using a baseurl different
          from the expected rootpath of qgis server api.
          For exemple, wfs3 request may be mapped to a completely different
          root path.
        """,
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
    host: str = Field("localhost", title="Hostname")
    port: int = Field(DEFAULT_PORT, title="Port")
    enable_tls: bool = Field(
        False,
        title="Enable TLS",
    )
    cafile: Option[FilePath] = Field(
        title="CA file",
    )
    client_key_file: Option[FilePath] = Field(
        title="TLS  key file",
        description="Path to the TLS key file",
    )
    client_cert_file: Option[FilePath] = Field(
        title="TLS Certificat",
        description="Path to the TLS certificat file",
    )
    title: str = Field(
        default="",
        title="A descriptive title",
    )
    description: str = Field(
        default="",
        title="A description of the service",
    )

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
    forward_headers: list[Annotated[str, StringConstraints(to_lower=True)]] = Field(
        default=["x-qgis-*", "x-lizmap-*"],
        title="Forwarded headers",
        description=(
            "Set the headers that will be forwarded to the Qgis server backend.\n"
            "This may be useful if you have plugins that may deal with request headers."
        ),
    )
    api: list[ApiEndpoint] = Field(
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
