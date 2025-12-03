import asyncio
import dataclasses

from contextlib import contextmanager
from io import BytesIO
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Iterator,
    Optional,
    Protocol,
    TypeAlias,
    cast,
)

from minio import Minio, commonconfig, datatypes
from minio.error import MinioException, S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

from qjazz_core.errors import QJazzException

from .models import DirResource, FileResource, ResourceType
from .reader import bucket_reader
from .writer import Object, ObjectWriteResult, bucket_destination


class StoreError(QJazzException):
    def __init__(self, status: int, message: str):
        self.status_code = status
        super().__init__(message)


@contextmanager
def store_error() -> Generator[None, None, None]:
    try:
        yield
    except S3Error as err:
        # See https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html#RESTErrorResponses
        # for s3 error responses
        raise StoreError(status=err.response.status, message=str(err)) from None
    except MinioException as err:
        raise StoreError(status=500, message=str(err)) from None


@dataclasses.dataclass
class StoreCreds:
    endpoint: str
    access_key: str
    secret_key: str
    region: Optional[str] = None
    secure: bool = True
    cert_check: bool = True


StoreClient: TypeAlias = Minio


def store_client(creds: StoreCreds) -> StoreClient:
    """Create store client"""
    return Minio(
        creds.endpoint,
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        region=creds.region,
        secure=creds.secure,
        cert_check=creds.cert_check,
    )


def _create_store(
    client: Minio,
    *,
    service: str,
    location: Optional[str] = None,
):
    """Create the store bucket"""
    # Create the bucket for the service
    if not client.bucket_exists(service):
        client.make_bucket(service, location=location)
        client.set_bucket_lifecycle(
            service,
            config=LifecycleConfig(
                [
                    Rule(
                        commonconfig.ENABLED,
                        rule_filter=commonconfig.Filter(prefix=""),
                        rule_id="qjazz_store_expiration",
                        expiration=Expiration(days=1),
                    ),
                ],
            ),
        )


async def create_store(
    store: StoreCreds | Minio,
    *,
    service: str,
    location: Optional[str] = None,
):
    if isinstance(store, StoreCreds):
        store = store_client(store)

    await asyncio.to_thread(_create_store, store, service=service, location=location)


async def push_object(
    client: Minio,
    stream: AsyncIterator[bytes],
    *,
    service: str,
    identity: str,
    obj: Object,
    metadata: Optional[dict[str, str]] = None,
) -> ObjectWriteResult:
    """Push streamed data to bucket"""
    writer = bucket_destination(client, service, prefix=identity)

    return await writer(obj, stream, metadata)


def pull_object(
    client: Minio,
    *,
    service: str,
    identity: str,
    obj: Object,
    part_size: Optional[int] = None,
) -> Iterator[bytes]:
    reader = bucket_reader(client, service, prefix=identity)
    with reader(obj) as r:
        while True:
            chunk = r.read(part_size)
            if not chunk:
                break
            yield chunk


class StreamWriter(Protocol):
    def __call__(
        self,
        obj: Object,
        stream: AsyncIterator[bytes],
        metadata: Optional[dict[str, str]] = None,
    ) -> Awaitable[FileResource]: ...


@contextmanager
def put_store(
    store: StoreCreds | Minio,
    *,
    service: str,
    identity: str,
) -> Generator[StreamWriter, None, None]:
    if isinstance(store, StoreCreds):
        store = store_client(store)

    # Push stream to store
    async def _push(
        obj: Object,
        stream: AsyncIterator[bytes],
        metadata: Optional[dict[str, str]] = None,
    ) -> FileResource:
        result = await push_object(
            store,
            stream,
            service=service,
            identity=identity,
            obj=obj,
            metadata=metadata,
        )

        # Metadata should contains the real object size in
        # case of data would be encrypted
        content_size = metadata.get("content-size", obj.size) if metadata else obj.size

        return FileResource(
            name=obj.name,
            size=content_size,
            content_type=obj.content_type,
            last_modified=result.last_modified,
            version=result.version_id,
        )

    with store_error():
        yield _push


META_PREFIX = "x-amz-meta-"


def to_resource(obj: datatypes.Object, root: str) -> ResourceType:
    """Convert Minio object to ResourceType"""
    res: ResourceType
    name = obj.object_name.removeprefix(root)  # type: ignore [union-attr]
    if obj.is_dir:
        res = DirResource(name=name)
    else:
        content_size = obj.size
        encrypted = False
        if obj.metadata:
            encrypted = obj.metadata.get(f"{META_PREFIX}encrypted") == "yes"
            content_size_meta = obj.metadata.get(f"{META_PREFIX}content-size")
            if content_size_meta:
                content_size = int(content_size_meta)

        res = FileResource(
            name=name,
            size=content_size,
            content_type=obj.content_type,
            last_modified=obj.last_modified,
            version=obj.version_id,
            encrypted=encrypted,
        )
    return res


async def list_store(
    store: StoreCreds | Minio,
    *,
    service: str,
    identity: str,
    prefix: Optional[str] = None,
    recurse: bool = False,
) -> list[ResourceType]:
    root = f"{identity}/"
    prefix = f"{root}{prefix or ''}"

    if isinstance(store, StoreCreds):
        store = store_client(store)

    def _resources() -> list[ResourceType]:
        objects = store.list_objects(service, prefix=prefix, recursive=recurse)

        return [to_resource(obj, root) for obj in objects if obj.object_name]

    with store_error():
        return await asyncio.to_thread(_resources)


async def stat_store(
    store: StoreCreds | Minio,
    name: str,
    *,
    service: str,
    identity: str,
) -> FileResource:
    """Get resource info"""
    if isinstance(store, StoreCreds):
        store = store_client(store)
    root = f"{identity}/"

    with store_error():
        obj = await asyncio.to_thread(store.stat_object, service, f"{root}{name}")

    return cast("FileResource", to_resource(obj, root))


async def delete_store(
    store: StoreCreds | Minio,
    name: str,
    *,
    service: str,
    identity: str,
    version_id: Optional[str] = None,
):
    """Delete resource"""
    if isinstance(store, StoreCreds):
        store = store_client(store)
    with store_error():
        await asyncio.to_thread(
            store.remove_object,
            service,
            f"{identity}/{name}",
            version_id=version_id,
        )


DecoderAdaptor = Callable[[BytesIO], Iterator[bytes]]


class StreamReader(Protocol):
    def __call__(self, obj: Object) -> AsyncIterator[bytes]: ...


@contextmanager
def get_store(
    store: StoreCreds | Minio,
    *,
    service: str,
    identity: str,
    part_size: Optional[int] = None,
    timeout: Optional[int] = None,
    decoder: Optional[DecoderAdaptor] = None,
) -> Generator[StreamReader, None, None]:
    """Pool object out of store asynchronously

    Usage:
    ```
    with get_store(
        vault,
        endpoint,
        access_key,
        secret_key,
        service=service,
        identity=identity,
    ) as get:
        obj = Object(name="myobject.data")
        async for chunk in get(obj):
            ...  # Do something with chunk
    ```
    """
    import queue

    # Mino client expected to be thread safe:
    # See https://github.com/minio/minio-go/issues/598
    if isinstance(store, StoreCreds):
        store = store_client(store)

    with store_error():
        reader = bucket_reader(store, service, prefix=identity)

    async def _get(obj: Object) -> AsyncIterator[bytes]:
        q: queue.Queue = queue.Queue()

        nonlocal decoder

        if not decoder:

            def _decode(r: BytesIO) -> Iterator[bytes]:
                chunk = r.read(part_size)
                while chunk:
                    yield chunk
                    chunk = r.read(part_size)

            decoder = _decode

        def _pull():
            try:
                with reader(obj) as r:
                    for block in decoder(r):
                        q.put(block)
                    q.put(b"")
            except Exception as e:
                q.put(e)

        pull_task = asyncio.create_task(asyncio.to_thread(_pull))
        try:
            while True:
                chunk = await asyncio.to_thread(q.get, timeout=timeout)
                if isinstance(chunk, Exception):
                    raise chunk
                if not chunk:
                    break
                yield chunk
        except queue.Empty:
            raise asyncio.TimeoutError() from None
        finally:
            exception = pull_task.exception()
            if exception:
                raise exception
            else:
                pull_task.cancel()

    with store_error():
        yield _get
