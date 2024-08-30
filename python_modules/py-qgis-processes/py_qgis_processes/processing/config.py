import sys

from pathlib import Path
from string import Template
from textwrap import dedent as _D

from pydantic import (
    AfterValidator,
    DirectoryPath,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
)
from typing_extensions import (
    Annotated,
    Dict,
    List,
    Optional,
)

from py_qgis_cache import ProjectsConfig
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config as BaseConfig,
)
from py_qgis_contrib.core.config import SSLConfig
from py_qgis_contrib.core.qgis import QgisPluginConfig

from .schemas import WGS84


def _validate_absolute_path(p: Path) -> Path:
    if not p.is_absolute():
        raise ValueError(f"Path {p} must be absolute")
    return p


def _validate_template(s: str | Template) -> Template:
    _t = Template(s) if not isinstance(s, Template) else s
    if sys.version_info >= (3, 11) and not _t.is_valid():
        raise ValueError(f"Invalid template: {s}")
    return _t


class _Template(Template):
    def __str__(self) -> str:
        return self.template


TemplateStr = Annotated[
    _Template,
    PlainValidator(_validate_template),
    PlainSerializer(lambda t: t.template, return_type=str),
    WithJsonSchema({'type': 'str'}),
]


# Processing job config section
class ProcessingConfig(BaseConfig):
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Projects and cache configuration",
    )
    plugins: QgisPluginConfig = Field(
        default=QgisPluginConfig(),
        title="Plugin configuration",
    )
    workdir: Annotated[
        DirectoryPath,
        AfterValidator(_validate_absolute_path),
    ] = Field(
        title="Working directory",
        description=_D(
            """
            Parent working directory where processes are executed.
            Each processes will create a working directory for storing
            result files and logs.
            """,
        ),
    )
    exposed_providers: List[str] = Field(
        default=['script', 'model'],
        title="Internal qgis providers exposed",
        description=_D(
            """
            List of exposed QGIS processing internal providers.
            NOTE: It is not recommended exposing all providers like
            `qgis` or `native`, instead provide your own wrapping
            algorithm, script or model.
            """,
        ),
    )
    expose_deprecated_algorithms: bool = Field(
        default=True,
        title="Expose deprecated algorithms",
        description=_D(
            """
            Expose algorithm wich have the `Deprecated`
            flag set.
            """,
        ),
    )
    # XXX Must set in Settings `default-output-vector-layer-ext`
    default_vector_file_ext: Optional[str] = Field(
        default="fgb",
        title="Default vector file extension",
        description=_D(
            """
            Define the default vector file extensions for vector destination
            parameters. If not specified, then the QGIS default value is used.
            """,
        ),
    )
    # XXX Must set in Settings `default-output-raster-layer-ext`
    default_raster_file_ext: Optional[str] = Field(
        default=None,
        title="Default vector file extension",
        description=_D(
            """
            Define the default raster file extensions for raster destination
            parameters. If not specified, then the QGIS default value is used.
            """,
        ),
    )
    adjust_ellipsoid: bool = Field(
        default=False,
        title="Force ellipsoid imposed by the source project",
        description=_D(
            """
            Force the ellipsoid from the src project into the destination project.
            This only apply if the src project has a valid CRS.
            """,
        ),
    )
    default_crs: str = Field(
        default=WGS84,
        title="Set default CRS",
        description=_D(
            """
            Set the CRS to use when no source map is specified.
            For more details on supported formats see the GDAL method
            'GdalSpatialReference::SetFromUserInput()'
            """,
        ),
    )
    advertised_services_url: TemplateStr = Field(
        default=_Template("ows:$jobId/$name"),
        validate_default=True,
        title="Advertised services urls",
        description="Url template used for  OGC services references.",
    )
    store_url: TemplateStr = Field(
        default=_Template("store:$jobId/$resource"),
        validate_default=True,
        title="Storage url",
        description="Url template for downloading resources",
    )
    raw_destination_input_sink: bool = Field(
        default=False,
        title="Use destination input as sink",
        description=_D(
            """
            Allow input value as sink for destination layers.
            This allow value passed as input value to be interpreted as
            path or uri sink definition. This enable passing any string
            that QGIS may use a input source but without open options except for the
            'layername=<name>' option.

            NOTE: Running concurrent jobs with this option may result in unpredictable
            behavior.

            For that reason it is considered as an UNSAFE OPTION and you should never enable
            this option if you are exposing the service publicly.

            File path inputs prefixed with '/' will correspond to path located in the root
            directory specified by the `raw_destination_root_path` option.
            Otherwise, they will be stored in the job folder.
            """,
        ),
    )
    raw_destination_root_path: Annotated[
        Optional[DirectoryPath],
        AfterValidator(lambda p: p and _validate_absolute_path(p)),
    ] = Field(
        default=None,
        title="Raw destination root path",
        description=_D(
            """
            Specify the root directory for storing destination layers files when
            the `raw_destination_input_sink` option is enabled.
            If not specified, files will be stored in the job folder.
            """,
        ),
    )
    certificats: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL Certificates",
        description="SSL credentials to use for references inputs",
    )

    max_cached_projects: int = Field(
        default=10,
        gt=0,
        title="Project cache size",
        description="The maximum number of projects in cache by process.",
    )

    def settings(self) -> Dict[str, str]:
        """Configure qgis processing settings
        """
        settings = {
            "qgis/configuration/prefer-filename-as-layer-name": "false",
            "Processing/Configuration/PREFER_FILENAME_AS_LAYER_NAME": "false",
       }

        # Set up folder settings
        paths = self.plugins.paths

        def _folders(name):
            for parent in paths:
                p = parent.joinpath(name)
                if p.is_dir():
                    yield p

        scripts_folders = ';'.join(str(p) for p in _folders('scripts'))
        if scripts_folders:
            logger.debug("Scripts folders set to %s", scripts_folders)
            settings["Processing/Configuration/SCRIPTS_FOLDERS"] = scripts_folders

        models_folders = ';'.join(str(p) for p in _folders('models'))
        if models_folders:
            logger.debug("Models folders set to %s", models_folders)
            settings["Processing/Configuration/MODELS_FOLDER"] = models_folders

        # Configure default vector extensions
        if self.default_vector_file_ext:
            from qgis.core import QgsVectorFileWriter
            exts = QgsVectorFileWriter.supportedFormatExtensions()
            ext = self.default_vector_file_ext
            idx = exts.index(ext)
            settings['qgis/configuration/default-output-vector-layer-ext'] = idx
            settings['qgis/configuration/default-output-vector-ext'] = self.default_vector_file_ext
            # Qgis > 33800

        # Configure default raster extensions
        if self.default_raster_file_ext:
            from qgis.core import QgsRasterFileWriter
            exts = QgsRasterFileWriter.supportedFormatExtensions()
            ext = self.default_raster_file_ext
            idx = exts.index(ext)
            settings['qgis/configuration/default-output-raster-layer-ext'] = idx
            settings['qgis/configuration/default-output-raster-ext'] = ext
            # Qgis > 33800

        return settings
