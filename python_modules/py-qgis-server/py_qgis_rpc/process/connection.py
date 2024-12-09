import os
import pickle  # nosec
import sys

from io import BytesIO
from pathlib import Path
from struct import pack, unpack

from typing_extensions import cast

from py_qgis_contrib.core import logger

from .messages import Message, MessageAdapter


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
        b = os.read(self._in, 4)
        # Take care if the parent close the connection then
        # read() will return an empty buffer (EOF)
        if b == b'':    # End of file: Parent closed the connection
            logger.error("Connection closed by parent")
            raise SystemExit(1)
        size, = unpack('!i', b)
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
        self.fd = os.open(path, os.O_WRONLY)
        self._busy = True

    def __del__(self):
        os.close(self.fd)

    def busy(self):
        if not self._busy:
            self._busy = True
            os.write(self.fd, b'\x01')

    def done(self):
        if self._busy:
            self._busy = False
            os.write(self.fd, b'\x00')
