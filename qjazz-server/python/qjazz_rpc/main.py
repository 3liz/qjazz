import os
import sys

from contextlib import closing
from typing import cast

from pydantic import ConfigDict, Field

from qjazz_contrib.core import config, logger

from .config import QgisConfig
from .connection import Connection, RendezVous
from .worker import qgis_server_run, setup_server

#
# This module is expected to be run
# as rpc module child process
#

WORKER_SECTION = "worker"


# Get the same hierarchy as the main configuration
# otherwise env variables wont apply
class WorkerConfig(config.ConfigBase):
    model_config = ConfigDict(extra="ignore")

    qgis: QgisConfig = Field(
        QgisConfig(),
        title="Qgis server configuration",
    )


def run(name: str, projects: list[str]) -> None:
    rendez_vous = RendezVous()

    confservice = config.ConfBuilder()
    confservice.add_section(WORKER_SECTION, WorkerConfig)
    confservice.validate({})

    if os.getenv("QJAZZ_DUMP_CONFIG") == "1":
        print(  # noqa T201
            "== Configuration ==\n",
            confservice.conf.model_dump_json(indent=4),
            flush=True,
            file=sys.stderr,
        )

    logger.setup_log_handler(confservice.conf.logging.level)

    # Create proxy for allow update
    qgis_conf = cast(QgisConfig, config.ConfigProxy(confservice, f"{WORKER_SECTION}.qgis"))

    with closing(Connection()) as connection:
        # Create QGIS server
        server = setup_server(qgis_conf)
        qgis_server_run(
            server,
            connection,
            qgis_conf,
            rendez_vous,
            name=f"{name}_{os.getpid()}",
            projects=projects,
        )


if __name__ == "__main__":
    import sys

    run(sys.argv[1], sys.argv[2:])
