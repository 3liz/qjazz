
from pydantic import DirectoryPath, Field
from typing_extensions import (
    Dict,
    List,
    Optional,
)

from py_qgis_cache import ProjectsConfig
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config as BaseConfig,
)
from py_qgis_contrib.core.config import (
    SSLConfig,
    section,
)
from py_qgis_contrib.core.qgis import QgisPluginConfig


# Processing job config section
@section('processing')
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
    exposed_providers: List[str] = Field(
        default=['script', 'model'],
        title="Internal qgis providers exposed",
        description=(
            "List of exposed QGIS processing internal providers.\n"
            "NOTE: It is not recommended exposing all providers like\n"
            "`qgis` or `native`, instead provide your own wrapping\n"
            "algorithm, script or model."
        ),
    )
    # XXX Must set in Settings `default-output-vector-layer-ext`
    default_vector_file_ext: Optional[str] = Field(
        default="fgb",
        title="Default vector file extension",
        description=(
            "Define the default vector file extensions for vector destination\n"
            "parameters. If not specified, then the QGIS default value is used."
        ),
    )
    # XXX Must set in Settings `default-output-raster-layer-ext`
    default_raster_file_ext: Optional[str] = Field(
        default=None,
        title="Default vector file extension",
        description=(
            "Define the default raster file extensions for raster destination\n"
            "parameters. If not specified, then the QGIS default value is used."
        ),
    )
    adjust_ellipsoid: bool = Field(
        default=False,
        title="Force ellipsoid imposed by the src project",
        description=(
            "Force the ellipsoid from the src project into the destination project.\n"
            "This only apply if the src project has a valid CRS."
        ),
    )
    default_crs: str = Field(
        default="EPSG:4326",
        title="Set default CRS",
        description=(
            "Set the CRS to use when no source map is specified.\n"
            "For more details on supported formats see the GDAL method\n"
            "'GdalSpatialReference::SetFromUserInput()'"
        ),
    )
    raw_destination_input_sink: bool = Field(
        default=False,
        title="Use destination input as sink",
        description=(
            "Allow input value as sink for destination layers.\n"
            "This allow value passed as input value to be interpreted as\n"
            "path or uri sink definition. This enable passing any string\n"
            "that QGIS may use a input source but without open options except for the\n"
            "'layername=<name>' option.\n"
            "NOTE: Running concurrent jobs with this option may result in unpredictable\n"
            "behavior."
            "For that reason it is considered as an UNSAFE OPTION and you should never enable\n"
            "this option if you are exposing the service publicly.\n"
            "\n"
            "File path inputs prefixed with '/' will correspond to path located in the root\n"
            "directory specified by the `raw_destination_root_path` option.\n"
            "Otherwise, they will be stored in the job folder.\n"
        ),
    )
    raw_destination_root_path: Optional[DirectoryPath] = Field(
        default=None,
        title="Raw destination root path",
        description=(
            "Specify the root directory for storing destination layers files when\n"
            "the `raw_destination_input_sink` option is enabled.\n"
            "If not specified, files will be stored in the job folder.\n"
        ),
    )
    certificats: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL Certificates",
        description="SSL credentials to use for references inputs",
    )

    def settings(self) -> Dict[str, str]:
        """Configure qgis processing settings
        """
        settings = {
            "qgis/configuration/prefer-filename-as-layer-name": "false",
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
            logger.info("Scripts folders set to %s", scripts_folders)
            settings["Processing/Configuration/SCRIPTS_FOLDERS"] = scripts_folders

        models_folders = ';'.join(str(p) for p in _folders('models'))
        if models_folders:
            logger.info("Models folders set to %s", scripts_folders)
            settings["Processing/Configuration/MODELS_FOLDER"] = models_folders

        # Configure default extensions
        if self.default_vector_file_ext:
            from qgis.core import QgsVectorFileWriter
            exts = QgsVectorFileWriter.supportedFormatExtensions()
            idx = exts.index(self.default_vector_file_ext)
            settings['qgis/configuration/default-output-vector-layer-ext'] = idx
        if self.default_raster_file_ext:
            from qgis.core import QgsRasterFileWriter
            exts = QgsRasterFileWriter.supportedFormatExtensions()
            idx = exts.index(self.default_raster_file_ext)
            settings['qgis/configuration/default-output-raster-layer-ext'] = idx

        return settings
