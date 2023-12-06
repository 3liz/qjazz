
from contextlib import contextmanager
from pathlib import Path

import grpc

from typing_extensions import List, Optional

from py_qgis_contrib.core.config import SSLConfig

from .._grpc import api_pb2_grpc


# Return a ChannelCredential struct
def _channel_credentials(files: SSLConfig):
    def _read(f) -> Optional[bytes]:
        if f:
            with Path(files.ca).open('rb') as fp:
                return fp.read()

    return grpc.ssl_channel_credentials(
        root_certificate=_read(files.ca),
        certificate=_read(files.cert),
        private_key=_read(files.key),
    )


@contextmanager
def stub(
    target: str,
    ssl: Optional[SSLConfig] = None,
    channel_options: Optional[List] = None,
    stub=None,
):
    # Return a synchronous client channel
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    #
    # For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html

    ssl_creds = _channel_credentials(ssl) if ssl else None

    with (
        grpc.secure_channel(
            target,
            ssl_creds,
            options=channel_options,
        )
        if ssl_creds
        else grpc.insecure_channel(
            target,
            options=channel_options,
        )
    ) as channel:
        stub = stub or api_pb2_grpc.QgisAdminStub
        yield stub(channel)
