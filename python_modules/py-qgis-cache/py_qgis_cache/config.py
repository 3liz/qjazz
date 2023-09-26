import os

from py_qgis_contrib.core import config
from pydantic import (
    Field,
    PlainValidator,
    PlainSerializer,
    WithJsonSchema,
    ValidationInfo,
    AfterValidator,
)
from typing_extensions import Dict, Annotated, Callable
from urllib.parse import urlsplit, urlunsplit, SplitResult


def _getenv_bool(varname: str) -> bool:
    return os.getenv(varname, 'no').lower() in ('1', 'yes', 'true')


def validate_url(v) -> SplitResult:
    if not isinstance(v, str):
        raise ValueError("Url must be of type str")
    url = urlsplit(v)
    if not url.scheme:
        url = url._replace(scheme='file')
    return url


Url = Annotated[
    SplitResult,
    PlainValidator(validate_url),
    PlainSerializer(lambda x: f'{urlunsplit(x)}', return_type=str),
    WithJsonSchema({'type': 'str'}),
]


def _qgis_env_flag_validator(name: str) -> Callable[[str, ValidationInfo], str]:
    def validator(v: bool, info: ValidationInfo) -> bool:
        return v or _getenv_bool(name)
    return validator


class ProjectsConfig(config.Config):
    strict_check: bool = Field(
        default=True,
        title="Enable strict checking",
        description=(
            "Activate strict checking of project layers. "
            "When enabled, Qgis projects with invalid layers will be dismissed. "
            "Trying to access such a project will lead to a 'unprocessable Entity' "
            "(422) HTTP error"
        )
    )
    trust_layer_metadata: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator('QGIS_TRUST_LAYER_METADATA')),
    ] = Field(
        default=False,
        title="Trust layer metadata",
        description=(
            "Trust layer metadata. "
            "Improves layer load time by skipping expensive checks "
            "like primary key unicity, geometry type and "
            "srid and by using estimated metadata on layer load. "
            "Since QGIS 3.16"
        )
    )
    disable_getprint: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator('QGIS_SERVER_DISABLE_GETPRINT')),
    ] = Field(
        default=False,
        title="Disable GetPrint requests",
        description=(
            "Don't load print layouts. "
            "Improves project read time if layouts are not required, "
            "and allows projects to be safely read in background threads "
            "(since print layouts are not thread safe)."
        )
    )
    force_readonly_layers: Annotated[
        bool,
        AfterValidator(_qgis_env_flag_validator('QGIS_SERVER_FORCE_READONLY_LAYERS')),
    ] = Field(
        default=False,
        title="Force read only mode",
        description="Force layers to open in read only mode"
    )
    disable_advertised_urls: bool = Field(
        default=False,
        title="Disable OWS advertised urls",
        description=(
            "Disable ows urls defined in projects. "
            "This may be necessary because Qgis projects "
            "urls override proxy urls"
        )
    )
    search_paths: Dict[str, Url] = Field(
        default={},
        title="Scheme mapping definitions",
        description=(
            "Defines mapping betweeen location base path and storage handler root url. "
            "Resource path relative to location will be joined the the root url path. "
            "In the case of Qgis storage, the handler is responsible for transforming "
            "the result url into a comprehensive format for the corresponding QgsProjectStorage "
            "implementation. "
            "This is handled by the default storage implementation for Qgis native project storage. "
            "In case of custom QgsProjectStorage, if the scheme does not allow passing project as "
            "path component, it is possible to specify a custom resolver function."
        )
    )
    allow_direct_path_resolution: bool = Field(
        default=True,
        title="Allow direct path resolution",
        description=(
            "Allow direct path resolution if there is "
            "no matching from the search paths. "
            "Uri are directly interpreted as valid Qgis project's path"
            "WARNING: allowing this may be a security vulnerabilty."
        )
    )
