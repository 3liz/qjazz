import os
import pickle  # nosec
import sys

from contextlib import closing
from io import BytesIO
from pathlib import Path
from struct import pack, unpack

from typing_extensions import cast

from py_qgis_contrib.core import config, logger

from ._op_config import WORKER_SECTION, WorkerConfig
from ._op_worker import qgis_server_run, setup_server
from .messages import Message, MessageAdapter

#
# This module is expected to be run
# as rpc module child process
#


class Connection:
    # Read and write data directly in binary format
    # by bypassing TextIOWrapper
    def __init__(self):
        self._in = sys.stdin.fileno()
        # Protect against spurious
        # write to stdout from QGIS, Python plugins
        # or child processes
        #
        # This is achieved by writing request I/0
        # to the original stdout device while redirecting
        # stdout to stderr.

        # Get the stdout file descriptor
        stdout_fd = sys.stdout.fileno()
        # Keep a copy as our actual output
        self._out = os.dup(stdout_fd)
        # Redirect to stderr
        os.dup2(sys.stderr.fileno(), stdout_fd)

        sys.stdout.flush()

    def close(self):
        # Close the duplicated file descriptor
        os.close(self._out)

    def recv(self) -> Message:
        size, = unpack('!i', os.read(self._in, 4))
        data = os.read(self._in, size)

        # Handle data larger than pipe size
        if len(data) < size:
            buf = BytesIO()
            buf.write(data)
            remaining = size - len(data)
            while remaining > 0:
                chunk = os.read(self._in, remaining)
                remaining -= len(chunk)
                buf.write(chunk)
            data = buf.getvalue()

        msg = pickle.loads(data)  # nosec
        if isinstance(msg, dict):
            return MessageAdapter.validate_python(msg)
        else:
            return cast(Message, msg)

    def send_bytes(self, data: bytes):
        os.write(self._out, pack('!i', len(data)))
        if data:
            os.write(self._out, data)


class RendezVous:
    def __init__(self):
        path = Path(os.environ["RENDEZ_VOUS"])
        if not path.exists():
            raise RuntimeError(f"No rendez vous at {path} !")
        self.fp = path.open('wb')
        self._busy = True

    def _write(self, data: bytes):
        self.fp.write(data)
        self.fp.flush()

    def busy(self):
        if not self._busy:
            self._busy = True
            self._write(b'\x01')

    def done(self):
        if self._busy:
            self._busy = False
            self._write(b'\x00')


def run(name: str) -> None:

    rendez_vous = RendezVous()

    confservice = config.ConfBuilder()
    confservice.add_section(WORKER_SECTION, WorkerConfig)
    confservice.validate({})

    logger.setup_log_handler(confservice.conf.logging.level)

    # Create proxy for allow update
    worker_conf = cast(WorkerConfig, config.ConfigProxy(confservice, WORKER_SECTION))

    with closing(Connection()) as connection:
        # Create QGIS server
        server = setup_server(worker_conf)
        qgis_server_run(
            server,
            connection,
            worker_conf,
            rendez_vous,
            name=name,
        )


if __name__ == '__main__':
    import sys
    run(sys.argv[1])
