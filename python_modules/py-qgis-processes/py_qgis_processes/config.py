#
# Processing worker
#
import os
import sys

from pathlib import Path
from textwrap import dedent as _D

from pydantic import Field
from typing_extensions import (
    Optional,
    Sequence,
    cast,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.condition import (
    assert_precondition,
)

from .celery import CeleryConfig
from .processing.config import ProcessingConfig
from .processing.schemas import LinkHttp

CONFIG_ENV_PATH = 'PY_QGIS_PROCESSES_WORKER_CONFIG'


def lookup_config_path() -> Optional[Path]:
    """ Determine config path location
    """
    p: Optional[Path] = None
    var = os.getenv(CONFIG_ENV_PATH)
    if var:
        # Path defined with environment MUST exists
        p = Path(var).expanduser()
        assert_precondition(p.exists(), f"File not found {p}")
    else:
        # Search in standards paths
        for search in (
            '/etc/py-qgis/processes/worker.toml',
            '~/.py-qgis/processes/worker.toml',
            '~/.config/py-qgis/processes/worker.toml',
        ):
            p = Path(search).expanduser()
            if p.exists():
                break
    return p


#
# Processing configuration
#

config.confservice.add_section('processing', ProcessingConfig, field=...)

#
# Worker configuration
#


@config.section('worker', field=...)
class WorkerConfig(CeleryConfig):
    """
    Worker configuration

    Configure celery worker settings
    """
    service_name: str = Field(
        title="Name of the service",
        description=_D(
            """
            Name used as location service name
            for initializing Celery worker.
            """,
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
    if configpath:
        print("=Reading configuration from:", configpath, file=sys.stderr, flush=True)  # noqa T201

        cnf = config.read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
    else:
        cnf = {}

    config.confservice.validate(cnf)

    conf = config.confservice.conf
    logger.setup_log_handler(conf.logging.level)
    # Do not propagate otherwise logging will echo
    # to Celery logger
    logger.logger().propagate = False
    return cast(ConfigProto, conf)


def dump_worker_config():
    """Dump configuration as toml configuration file
    """
    config.confservice.dump_toml_schema(sys.stdout)
