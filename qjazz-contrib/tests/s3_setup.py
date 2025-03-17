from qjazz_cache import CacheManager, ProjectsConfig
from qjazz_contrib.core import logger
from qjazz_contrib.core.qgis import init_qgis_application

logger.setup_log_handler(logger.LogLevel.DEBUG)

init_qgis_application()

projects = ProjectsConfig(
    force_readonly_layers=True,
    search_paths={"/": "s3://test"},
    handlers={
        "s3": {
            "handler": "qjazz_cache.handlers.s3.S3ProtocolHandler",
            "config": dict(
                endpoint="localhost:9000",
                access_key="minioadmin",
                secret_key="minioadmin",
                secure=False,
            ),
        },
    },
)

CacheManager.initialize_handlers(projects)
