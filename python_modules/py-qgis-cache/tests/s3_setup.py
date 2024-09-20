import os

from py_qgis_cache import CacheManager, ProjectsConfig
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.qgis import init_qgis_application

logger.setup_log_handler(logger.LogLevel.DEBUG)

init_qgis_application()

# Test for environment configuration
os.environ['CONF_STORAGE_S3_ENDPOINT'] = "localhost:9000"

projects = ProjectsConfig(
    force_readonly_layers=True,
    search_paths={"/": "s3://test"},
    handlers={
        "s3": {
            "handler": "py_qgis_cache.handlers.s3.S3ProtocolHandler",
            "config": dict(
                # endpoint="localhost:9000",
                access_key="minioadmin",
                secret_key="minioadmin",
                secure=False,
            ),
        },
    },

)

CacheManager.initialize_handlers(projects)
