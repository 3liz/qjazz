#
# Implement Traversable object for
# bucket
#
# Implement a subset of pathlib.Path methods
#
from contextlib import _GeneratorContextManager, contextmanager
from pathlib import PurePosixPath
from typing import Any, Callable, Generator, Optional

from minio import Minio

from qjazz_core.condition import assert_precondition

from .writer import Object


def bucket_reader(
    client: Minio,
    bucket: str,
    prefix: Optional[str] = None,
) -> Callable[[Object], _GeneratorContextManager[Any]]:
    """Read from bucket objects

    Returns a reader factory for a given Object
    that return an object with a 'read' method
    """

    @contextmanager
    def open(obj: Object) -> Generator[Any, None, None]:
        assert_precondition(obj.name, "Object must have a valid name")  # type: ignore [arg-type]
        if prefix:
            object_name = str(PurePosixPath(prefix, obj.name))
        else:
            object_name = obj.name

        # Minio return an urllib3.response.HTTPResponse
        # which have a 'read' method
        response = client.get_object(bucket, object_name)
        try:
            yield response
        finally:
            response.close()
            response.release_conn()

    return open
