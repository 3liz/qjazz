from py_qgis_contrib.core import config


class ProcessingConfig(config.Config):
    exposed_providers: List[str] = Field(
        default=['script','model'],
        title="Internal qgis providers exposed",
        description=(
            "List of exposed QGIS processing internal providers.\n",
            "NOTE: It is not recommended exposing all providers like\n"
            "`qgis` or `native`, instead provide your own wrapping\n"
            "algorithm, script or model".
        )
    )
    vector_default_filext: str = Field(
        default=None,
        title="Default vector file extension",
        description=(
            "Define the default vector file extensions for vector destination\n"
            "parameters. If not specified, then the QGIS default value is used."
        ), 
    )
    raster_default_filext: str = Field(
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
            "'GRSpatialReference::SetFromUserInput()'"
        )
    )


class WorkerConfig(config.Config):
    """  Processing worker configuration
    """
    max_runs_per_worker: int = Field(
        default=1,
        description=(
            "Set the max number of runs that a worker\n"
            "can handle before reseting itself (i.e restart\n"
            "the Qgis process)."
        )
    )
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Projects and cache configuration",
    )
    plugins: QgisPluginConfig = Field(
        default=QgisPluginConfig(),
        title="Plugins configuration",
    )
    process_timeout: int = Field(
        default=20,
        title="Stalled process timeout",
        description=(
            "Set the amount of time in seconds before considering\n"
            "considering that a process is stalled.\n"
        ),
    )

