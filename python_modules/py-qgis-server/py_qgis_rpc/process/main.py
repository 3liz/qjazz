import sys

from contextlib import closing

from typing_extensions import cast

from py_qgis_contrib.core import config, logger

from .config import QgisConfig
from .connection import Connection, RendezVous
from .worker import qgis_server_run, setup_server

#
# This module is expected to be run
# as rpc module child process
#

QGIS_SECTION = "qgis"


def run(name: str) -> None:

    rendez_vous = RendezVous()

    confservice = config.ConfBuilder()
    confservice.add_section(QGIS_SECTION, QgisConfig)
    confservice.validate({})

    logger.setup_log_handler(confservice.conf.logging.level)

    # Create proxy for allow update
    qgis_conf = cast(QgisConfig, config.ConfigProxy(confservice, QGIS_SECTION))

    with closing(Connection()) as connection:
        # Create QGIS server
        server = setup_server(qgis_conf)
        qgis_server_run(
            server,
            connection,
            qgis_conf,
            rendez_vous,
            name=name,
        )


if __name__ == '__main__':
    import sys
    run(sys.argv[1])
