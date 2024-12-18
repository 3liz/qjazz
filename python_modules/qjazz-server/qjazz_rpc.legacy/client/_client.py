
from contextlib import contextmanager
from pathlib import Path

import grpc

from typing_extensions import Callable, List, Optional

from qjazz_contrib.core.config import SSLConfig

from .._grpc import qjazz_pb2_grpc


@contextmanager
def stub(
    address: str,
    ssl: Optional[SSLConfig] = None,
    channel_options: Optional[List] = None,
    stub: Optional[Callable] = None,
):
    # Return a synchronous client channel
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    #
    # For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
    def _read_if(f: Optional[Path]) -> Optional[bytes]:
        if f:
            with f.open('rb') as fp:
                return fp.read()
        else:
            return None

    with (
        grpc.secure_channel(
            address,
            grpc.ssl_channel_credentials(
                root_certificate=_read_if(ssl.cafile),
                certificate=_read_if(ssl.certfile),
                private_key=_read_if(ssl.keyfile),
            ),
            options=channel_options,
        )
        if ssl
        else grpc.insecure_channel(
            address,
            options=channel_options,
        )
    ) as channel:
        stub = stub or qjazz_pb2_grpc.QgisAdminStub
        yield stub(channel)
