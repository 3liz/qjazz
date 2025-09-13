from io import BytesIO
from typing import (
    AsyncGenerator,
    BinaryIO,
    Optional,
)

from pydantic import TypeAdapter
from qjazz_core.celery import JobContext
from qjazz_store import (
    FileResource,
    Object,
    StoreClient,
    StoreCreds,
    delete_store,
    get_store,
    put_store,
    stat_store,
    store_client,
)


def get_client(ctx: JobContext) -> StoreClient:
    """Returns store client"""
    # Wrapped data can only be read once
    creds = ctx.store_creds
    return store_client(
        StoreCreds(
            creds["endpoint"],
            access_key=creds["access_key"],
            secret_key=creds["secret_key"],
            secure=TypeAdapter(bool).validate_python(creds["secure"]),
        ),
    )


class Store:
    def __init__(self, ctx: JobContext):
        self._ctx = ctx
        self._client: Optional[StoreClient] = None

    def _get_client(self) -> StoreClient:
        if not self._client:
            self._client = get_client(self._ctx)
        return self._client

    async def stat(self, name: str) -> FileResource:
        """Stat resource"""
        return await stat_store(
            self._get_client(),
            name,
            service=self._ctx.service,
            identity=self._ctx.identity,
        )

    async def delete(self, name: str, version_id: Optional[str] = None):
        """Delete resource"""
        await delete_store(
            self._get_client(),
            name,
            service=self._ctx.service,
            identity=self._ctx.identity,
            version_id=version_id,
        )

    async def stream(
        self,
        name: str,
    ) -> AsyncGenerator[bytes, None]:
        """Open a resource a stream"""
        with get_store(
            self._get_client(),
            service=self._ctx.service,
            identity=self._ctx.identity,
            part_size=1024 * 1024,
        ) as get:
            obj = Object(name=name)
            async for chunk in get(obj):
                yield chunk

    async def readinto(self, name: str, writer: BinaryIO) -> int:
        """Read resource data into IO writer"""
        count = 0
        async for chunk in self.stream(name):
            count += writer.write(chunk)
        return count

    async def read(self, name: str) -> bytes:
        """Read all data from resource"""
        buf = BytesIO()
        await self.readinto(name, buf)
        return buf.getvalue()

    async def writefrom(
        self,
        name: str,
        reader: BinaryIO,
        *,
        content_type: Optional[str] = None,
        content_length: Optional[int] = None,
    ) -> FileResource:
        """Write resource from async stream"""

        async def stream() -> AsyncGenerator[bytes, None]:
            chunksize = 1024 * 1024
            chunk = reader.read(chunksize)
            while chunk:
                yield chunk
                chunk = reader.read(chunksize)

        with put_store(
            self._get_client(),
            service=self._ctx.service,
            identity=self._ctx.identity,
        ) as put:
            obj = Object(
                name=name,
                content_type=content_type,
                size=content_length,
            )
            return await put(obj, stream())

    async def write(
        self,
        name: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        content_length: Optional[int] = None,
    ) -> FileResource:
        """Write resource from  bytes"""
        return await self.writefrom(
            name,
            BytesIO(data),
            content_type=content_type,
            content_length=content_length,
        )
