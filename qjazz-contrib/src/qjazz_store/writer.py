import asyncio
import dataclasses

from datetime import datetime
from pathlib import PurePosixPath
from typing import (
    AsyncIterator,
    Awaitable,
    BinaryIO,
    Callable,
    Dict,
    Optional,
    cast,
)

from minio import Minio
from minio.api import ObjectWriteResult

from qjazz_core.condition import assert_precondition


@dataclasses.dataclass(kw_only=True)
class Object:
    name: str  # Used as file name
    size: Optional[int] = None  # Size in bytes (estimated)
    content_type: Optional[str] = None  # Expected content type
    mtime: Optional[datetime] = None  # Modification time if available


#
# Asynchronously put_object from an async stream
#
# See https://min.io/docs/minio/linux/developers/python/API.html#put_object
# for options details.
#
# According to https://github.com/minio/minio-go/issues/598,
# they should be no problem for executing minio request in parallel.
#
async def put_object_from_stream(
    client: Minio,
    stream: AsyncIterator[bytes],
    bucket_name: str,
    object_name: str,
    length: int,
    content_type: str = "application/octet-stream",
    part_size: int = 0,
    num_parallel_uploads: int = 3,
    **kwargs,
) -> ObjectWriteResult:
    import queue

    q = queue.Queue()  # type: ignore [var-annotated]
    # Reader object to be passed to put_object()

    class _Reader:
        def __init__(self):
            self._is_eof = False
            self._left = b""

        def read(self, size: int) -> bytes:
            """Return *at most* size bytes"""
            if self._is_eof:
                return b""
            elif self._left:
                data, self._left = self._left, b""
                return data
            else:
                b = q.get(block=True)
                sz = len(b)
                self._is_eof = sz == 0
                if size <= 0 or sz <= size:
                    return b
                else:
                    self._left = b[size:]
                    return b[:size]

    def _put_object() -> ObjectWriteResult:
        # See https://github.com/minio/minio-py/blob/master/minio/api.py
        return client.put_object(
            bucket_name,
            object_name,
            cast(BinaryIO, _Reader()),
            length=length,
            content_type=content_type,
            part_size=part_size,
            num_parallel_uploads=num_parallel_uploads,
            **kwargs,
        )

    async def _push():
        try:
            async for chunk in stream:
                q.put_nowait(chunk)
        finally:
            q.put_nowait(b"")

    group = asyncio.gather(_push(), asyncio.to_thread(_put_object))
    try:
        _, result = await group
        return result
    except Exception:
        group.cancel()
        raise


DEFAULT_PART_SIZE = 10 * 1024 * 1024  # 10Mo
# Minio require a minimum part_size of 5Mo
MIN_PART_SIZE = 5 * 1024 * 1024


def bucket_destination(
    client: Minio,
    bucket_name: str,
    prefix: Optional[str] = None,
    num_parallel_uploads: int = 3,
    part_size: int = DEFAULT_PART_SIZE,
    metadata: Optional[Dict[str, str]] = None,
) -> Callable[[Object, AsyncIterator[bytes], Optional[Dict[str, str]]], Awaitable[ObjectWriteResult]]:
    """Stream to s3 bucket"""
    part_size = max(MIN_PART_SIZE, part_size)

    async def _writer(
        obj: Object,
        stream: AsyncIterator[bytes],
        metadata: Optional[Dict[str, str]] = None,
    ) -> ObjectWriteResult:
        assert_precondition(obj.name, "Object must have a valid name")  # type: ignore [arg-type]
        if prefix:
            object_name = str(PurePosixPath(prefix, obj.name))
        else:
            object_name = obj.name

        if obj.size is None or obj.size < 0:
            size = -1
        else:
            size = obj.size

        return await put_object_from_stream(
            client,
            stream,
            bucket_name,
            object_name,
            length=size,
            content_type=obj.content_type or "application/octet-stream",
            part_size=part_size,
            num_parallel_uploads=num_parallel_uploads,
            metadata=metadata,
        )

    return _writer
