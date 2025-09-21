import asyncio
import dataclasses
import importlib.resources

from io import BytesIO
from typing import TYPE_CHECKING, cast

import minio
import pytest

from qjazz_store import (
    Object,
    StoreClient,
    StoreCreds,
    access,
    push_object,
)
from qjazz_store import (
    store_client as _store_client,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_store_resource_files() -> None:
    root = cast("Path", importlib.resources.files("qjazz_store").joinpath("templates"))
    assert root.exists()

    path = root.joinpath("store-policy.json")
    assert path.is_file()


def test_store_policy_file():
    with access._read_policy("myservice", "myidentity") as policy_file:
        content = policy_file.open().read()
        print("\n==Storage policy:\n", content)
    # Check policy_file is removed
    assert not policy_file.exists()


@pytest.mark.minio
async def test_store_push_object(store_client: StoreClient):
    """Test aysnc write to bucket destination"""
    data = b"loremipsum" * 2048
    chunk_size = len(data) // 2
    service = "dev"
    identity = "test"
    name = "test_push_object.data"

    print("\n::test_store_push_object::client:", store_client)
    return

    # Fake an asynchronous stream
    async def _stream():
        io = BytesIO(data)
        while True:
            chunk = io.read(chunk_size)
            if not chunk:
                break
            yield chunk
            await asyncio.sleep(0.1)

    await push_object(
        store_client,
        _stream(),
        service=service,
        identity=identity,
        obj=Object(name=name),
    )

    # Retrieve data
    response = store_client.get_object(service, f"{identity}/{name}")
    content = response.read(len(data))

    assert content == data


@pytest.mark.minio
async def test_store_access(store_creds: StoreCreds):
    """Test storage access creation"""
    service = "myservice"
    identity = "myidentity"

    access_key, secret_key, _expiration = await access.create_store_access(
        store_creds,
        service=service,
        identity=identity,
        ttl=30,
    )

    # Attempt access
    client = _store_client(
        dataclasses.replace(
            store_creds,
            access_key=access_key,
            secret_key=secret_key,
        ),
    )

    wr = client.put_object(
        service,
        f"{identity}/test",
        BytesIO(b"foo"),
        length=3,
    )
    print("==Storage write result: ", wr)

    with pytest.raises(minio.error.S3Error):
        client.put_object(
            service,
            "notallowed/test",
            BytesIO(b"foo"),
            length=3,
        )
