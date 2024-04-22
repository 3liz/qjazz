#
# Processing worker
#
from pathlib import Path

from pydantic import Field
from typing_extensions import (
    List,
    Optional,
)

from py_qgis_cache import ProjectsConfig
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config as BaseConfig,
)
from py_qgis_contrib.core.config import (
    confservice,
    read_config_json,
    read_config_toml,
    section,
)
from py_qgis_contrib.core.qgis import QgisPluginConfig

from ._celery import CeleryConfig

#
# Worker configuration
#


@section('worker', field=...)
class WorkerConfig(CeleryConfig):
    service_name: str = Field(
        title="Name of the service",
        description=(
            "Name used as location service name\n"
            "for initializing Celery worker."
        ),
    )
    routing_name: Optional[str] = None


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
    vector_default_filext: Optional[str] = Field(
        default=None,
        title="Default vector file extension",
        description=(
            "Define the default vector file extensions for vector destination\n"
            "parameters. If not specified, then the QGIS default value is used."
        ),
    )
    raster_default_filext: Optional[str] = Field(
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


def load_configuration(configpath: Path) -> BaseConfig:

    reader = (
        read_config_json
            if configpath.suffix == ".json"
            else read_config_toml
        )
    cnf = reader(
        configpath,
        location=str(configpath.parent.absolute()),
    )
    confservice.validate(cnf)
    conf = confservice.conf
    logger.setup_log_handler(conf.logging.level)
    return conf
