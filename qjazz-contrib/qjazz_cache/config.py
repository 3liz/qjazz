import os

from textwrap import dedent as _D
from typing import Annotated, Callable
from urllib.parse import SplitResult, urlsplit

from pydantic import (
    AfterValidator,
    Field,
    PlainSerializer,
    PlainValidator,
    PrivateAttr,
    TypeAdapter,
    ValidationInfo,
    WithJsonSchema,
)

from qjazz_contrib.core import config

from .handlers import HandlerConfig

Bool = TypeAdapter(bool)


def _getenv_bool(varname: str) -> bool:
    return Bool.validate_python(os.getenv(varname, "no"))


def validate_url(v: str) -> SplitResult:
    if not isinstance(v, str):
        raise ValueError("Url must be of type str")
    url = urlsplit(v)
    if not url.scheme:
        url = url._replace(scheme="file")
    return url


Url = Annotated[
    SplitResult,
    PlainValidator(validate_url),
    PlainSerializer(lambda x: x.geturl(), return_type=str),
    WithJsonSchema({"type": "str"}),
]


def _qgis_env_flag_validator(name: str) -> Callable[[bool, ValidationInfo], bool]:
    def validator(v: bool, info: ValidationInfo) -> bool:
        return v or _getenv_bool(name)

    return validator


class ProjectsConfig(config.ConfigBase):
    trust_layer_metadata: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator("QGIS_TRUST_LAYER_METADATA")),
    ] = Field(
        default=False,
        title="Trust layer metadata",
        description=(
            "Trust layer metadata.\n"
            "Improves layer load time by skipping expensive checks\n"
            "like primary key unicity, geometry type and\n"
            "srid and by using estimated metadata on layer load.\n"
            "Since QGIS 3.16"
        ),
    )
    disable_getprint: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator("QGIS_SERVER_DISABLE_GETPRINT")),
    ] = Field(
        default=False,
        title="Disable GetPrint requests",
        description=(
            "Don't load print layouts.\n"
            "Improves project read time if layouts are not required,\n"
            "and allows projects to be safely read in background threads\n"
            "(since print layouts are not thread safe)."
        ),
    )
    force_readonly_layers: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator("QGIS_SERVER_FORCE_READONLY_LAYERS")),
    ] = Field(
        default=True,
        title="Force read only mode",
        description="Force layers to open in read only mode",
    )
    ignore_bad_layers: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator("QGIS_SERVER_IGNORE_BAD_LAYERS")),
    ] = Field(
        default=False,
        title="Ignore bad layers",
        description=(
            "Allow projects to be loaded with event if it contains\n"
            "layers that cannot be loaded\n"
            "Note that the 'dont_resolve_layers flag' trigger automatically\n"
            "this option."
        ),
    )

    # Don't resolve layer paths
    # Don't load any layer content
    # Improve loading time when actual layer data is
    # not required.
    _dont_resolve_layers: bool = PrivateAttr(default=False)

    @property
    def dont_resolve_layers(self) -> bool:
        return self._dont_resolve_layers

    disable_advertised_urls: bool = Field(
        default=False,
        title="Disable OWS advertised urls",
        description=(
            "Disable ows urls defined in projects.\n"
            "This may be necessary because Qgis projects\n"
            "urls override proxy urls."
        ),
    )
    search_paths: dict[str, Url] = Field(
        default={},
        title="Scheme mapping definitions",
        description=(
            "Defines mapping betweeen location base path and storage handler root url.\n"
            "Resource path relative to location will be joined the the root url path.\n"
            "In the case of Qgis storage, the handler is responsible for transforming\n"
            "the result url into a comprehensive format for the corresponding\n"
            "QgsProjectStorage implementation.\n"
            "This is handled by the default storage implementation for Qgis native\n"
            "project storage. "
            "In case of custom QgsProjectStorage, if the scheme does not allow passing\n"
            "project as path component, it is possible to specify a custom resolver function."
        ),
    )
    allow_direct_path_resolution: bool = Field(
        default=True,
        title="Allow direct path resolution",
        description=(
            "Allow direct path resolution if there is\n"
            "no matching from the search paths.\n"
            "Uri are directly interpreted as valid Qgis project's path.\n"
            "WARNING: allowing this may be a security vulnerabilty."
        ),
    )

    handlers: dict[str, HandlerConfig] = Field(
        {},
        title="Project storage Handler configurations",
        description=(
            "Configure storage handlers.\nThe name will be used as scheme for project's search path\nconfiguration."
        ),
        examples=[
            _D(
                """
                [projects.search_paths]
                "/public/location1/" = "postgres1://?dbname=mydatabase1"
                "/public/location2/" = "postgres1://?dbname=mydatabase2"

                [projects.handlers.postgres1]
                handler_class = qjazz_cache.handlers.postgresql.PostgresHandler

                [projects.handlers.postgres1.config]
                uri = "postgresql://user@host/?schema=myschema"
                """,
            ),
        ],
    )
