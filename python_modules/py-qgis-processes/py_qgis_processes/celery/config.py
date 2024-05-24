#
# Processing worker
#
from pathlib import Path

from pydantic import Field

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

# Re-export
from ..processing.config import ProcessingConfig  # noqa F401
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
