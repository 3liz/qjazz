#
# Processing worker
#
import os
import sys

from pathlib import Path
from typing import (
    Optional,
    Protocol,
    Sequence,
    cast,
)

from qjazz_contrib.core import config, logger
from qjazz_contrib.core.celery import CeleryConfig
from qjazz_contrib.core.condition import (
    assert_precondition,
)
from qjazz_contrib.core.models import Field
from qjazz_processes.schemas import LinkHttp

from ..callbacks import CallbacksConfig
from ..processing.config import ProcessingConfig
from .storage import StorageConfig

CONFIG_ENV_PATH = "QJAZZ_PROCESSES_CONFIG"


def lookup_config_path() -> Optional[Path]:
    """Determine config path location"""
    p: Optional[Path] = None
    var = os.getenv(CONFIG_ENV_PATH)
    if var:
        # Path defined with environment MUST exists
        p = Path(var).expanduser()
        assert_precondition(p.exists(), f"File not found {p}")
    else:
        # Search in standards paths
        for search in (
            "/etc/qjazz/processes/service.toml",
            "~/.qjazz/processes/service.toml",
            "~/.config/qjazz/processes/service.toml",
        ):
            p = Path(search).expanduser()
            if p.exists():
                break
        else:
            p = None

    return p


#
# Worker configuration
#


@config.section("worker", field=...)
class WorkerConfig(CeleryConfig):
    """
    Worker configuration

    Configure celery worker settings
    """

    service_name: str = Field(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-]+$",
        title="Name of the service",
        description="""
        Name used as location service name
        for initializing Celery worker.
        """,
    )

    title: str = Field("", title="Service short title")

    description: str = Field("", title="Service description")

    links: Sequence[LinkHttp] = Field(
        default=(),
        title="Service related links",
    )

    cleanup_interval: int = Field(
        default=3600,
        ge=300,
        title="Cleanup interval",
        description="""
        Interval is seconds between two cleanup of expired jobs.
        The minimun is 300s (5mn).
        """,
    )

    reload_monitor: Optional[Path] = Field(
        default=None,
        title="Reload watch file",
        description="""
        The file to watch for reloading processing plugins.
        When the the modified time of the file is changed, processing
        providers are reloaded.
        The restart is graceful, all running jobs are terminated normally.
        """,
    )


# Allow type validation
class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    processing: ProcessingConfig
    worker: WorkerConfig
    storage: StorageConfig
    callbacks: CallbacksConfig

    def model_dump_json(*args, **kwargs) -> str: ...


confservice = config.ConfBuilder()

#
# Add processing/storage configuration
#

confservice.add_section("processing", ProcessingConfig, field=...)
confservice.add_section("storage", StorageConfig)
confservice.add_section("callbacks", CallbacksConfig)


def load_configuration() -> ConfigProto:
    """Load worker configuration"""
    configpath = lookup_config_path()
    if configpath:
        print("=Reading configuration from:", configpath, file=sys.stderr, flush=True)  # noqa T201

        cnf = config.read_config_toml(configpath)
    else:
        cnf = {}

    confservice.validate(cnf)
    confservice.register_as_service()

    conf = confservice.conf
    logger.setup_log_handler(conf.logging.level)
    # Do not propagate otherwise logging will echo
    # to Celery logger
    logger.logger().propagate = False
    return cast(ConfigProto, conf)


def dump_worker_config() -> None:
    """Dump configuration as toml configuration file"""
    confservice.dump_toml_schema(sys.stdout)
