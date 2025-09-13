import os

from textwrap import dedent
from typing import Annotated, cast

from pydantic import (
    PlainSerializer,
    PlainValidator,
    PrivateAttr,
    TypeAdapter,
    WithJsonSchema,
)

from qjazz_core import config
from qjazz_core.models import Field

from .handlers import HandlerConfig
from .routes import Routes

Bool = TypeAdapter(bool)


def _getenv_bool(varname: str, default: bool) -> bool:
    return Bool.validate_python(os.getenv(varname, default))


def validate_routes(v: str | dict[str, str]) -> Routes:
    match v:
        case str():
            v = TypeAdapter(dict[str, str]).validate_json(v)
        case dict():
            pass
        case _:
            raise ValueError("Mapping or json string expected")
    return Routes(cast("dict", v))


RoutesDef = Annotated[
    Routes,
    PlainValidator(validate_routes),
    PlainSerializer(
        lambda routes: {k: v.geturl() for k, v in routes.cannonical},
        return_type=dict[str, str],
    ),
    WithJsonSchema(TypeAdapter(dict[str, str]).json_schema()),
]


class ProjectsConfig(config.ConfigBase):
    trust_layer_metadata: bool = Field(
        default=_getenv_bool("QGIS_TRUST_LAYER_METADATA", False),
        title="Trust layer metadata",
        description="""
        Trust layer metadata.
        Improves layer load time by skipping expensive checks
        like primary key unicity, geometry type and
        srid and by using estimated metadata on layer load.
        Since QGIS 3.16
        """,
    )
    disable_getprint: bool = Field(
        default=_getenv_bool("QGIS_SERVER_DISABLE_GETPRINT", False),
        title="Disable GetPrint requests",
        description="""
        Don't load print layouts.
        Improves project read time if layouts are not required,
        and allows projects to be safely read in background threads
        (since print layouts are not thread safe).
        """,
    )
    force_readonly_layers: bool = Field(
        default=_getenv_bool("QGIS_SERVER_FORCE_READONLY_LAYERS", True),
        title="Force read only mode",
        description="Force layers to open in read only mode",
    )
    ignore_bad_layers: bool = Field(
        default=_getenv_bool("QGIS_SERVER_IGNORE_BAD_LAYERS", False),
        title="Ignore bad layers",
        description="""
        Allow projects to be loaded with event if it contains
        layers that cannot be loaded.
        Note that the 'dont_resolve_layers flag' trigger automatically
        this option.
        """,
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
    search_paths: RoutesDef = Field(
        default={},
        validate_default=True,
        title="Scheme mapping definitions",
        description="""
        Defines mapping betweeen location base path and storage handler root url.
        Resource path relative to location will be joined the the root url path.
        In the case of Qgis storage, the handler is responsible for transforming
        the result url into a comprehensive format for the corresponding
        QgsProjectStorage implementation.
        This is handled by the default storage implementation for Qgis native
        project storage.
        In case of custom QgsProjectStorage, if the scheme does not allow passing
        project as path component, it is possible to specify a custom resolver function.
        """,
    )
    allow_direct_path_resolution: bool = Field(
        default=False,
        title="Allow direct path resolution",
        description="""
        Allow direct path resolution if there is
        no matching from the search paths.
        Uri are directly interpreted as valid Qgis project's path.
        WARNING: allowing this may be a security vulnerabilty."
        """,
    )

    handlers: dict[str, HandlerConfig] = Field(
        {},
        title="Project storage Handler configurations",
        description="""
        Configure storage handlers.
        The name will be used as scheme for project's search path
        configuration.
        """,
        examples=[
            dedent(
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
