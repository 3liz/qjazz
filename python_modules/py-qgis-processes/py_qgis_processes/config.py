#
# Processing worker
#
import os
import sys

from pathlib import Path

from pydantic import Field
from typing_extensions import (
    Sequence,
    cast,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.condition import (
    assert_precondition,
)

from .celery import CeleryConfig
from .processing import (
    ProcessingConfig,
)
from .processing.schemas import LinkHttp


def lookup_config_path() -> Path:
    """ Determine config path location
    """
    var = os.getenv('PY_QGIS_PROCESSES_WORKER_CONFIG')
    if var:
        # Path defined with environment MUST exists
        p = Path(var).expanduser()
        assert_precondition(p.exists(), f"File not found {p}")
    else:
        # Search in standards paths
        for search in (
            '/etc/py-qgis-processes/worker.toml',
            '~/.py-qgis-processes/worker.toml',
            '~/.config/py-qgis-processes/worker.toml',
        ):
            p = Path(search).expanduser()
            if p.exists():
                break
        else:
            raise RuntimeError("No configuration found")

    print("=Reading configuration from:", p, file=sys.stderr, flush=True)  # noqa T201
    return p


#
# Worker configuration
#

@config.section('worker', field=...)
class WorkerConfig(CeleryConfig):
    service_name: str = Field(
        title="Name of the service",
        description=(
            "Name used as location service name\n"
            "for initializing Celery worker."
        ),
    )
    title: str = Field("", title="Service short title")
    description: str = Field("", title="Service description")
    links: Sequence[LinkHttp] = Field(
        default=(),
        title="Service related links",
    )


# Allow type validation
class ConfigProto:
    processing: ProcessingConfig
    worker: WorkerConfig


def load_configuration() -> ConfigProto:
    """ Load worker configuration
    """
    configpath = lookup_config_path()
    cnf = config.read_config_toml(
        configpath,
        location=str(configpath.parent.absolute()),
    )
    config.confservice.validate(cnf)

    conf = config.confservice.conf
    logger.setup_log_handler(conf.logging.level)
    return cast(ConfigProto, conf)


def dump_worker_config():
    """Dump configuration as toml configuration file
    """
    config.confservice.dump_toml_schema(sys.stdout)
