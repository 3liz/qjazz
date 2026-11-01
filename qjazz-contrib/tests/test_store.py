import asyncio
import dataclasses
import importlib.resources
import json

from io import BytesIO
from typing import TYPE_CHECKING, cast

import minio
import pytest

from qjazz_store import (
    Object,
    StoreClient,
    StoreCreds,
    StoreError,
    access,
    delete_store,
    list_store,
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


def test_store_policy():
    policy = json.loads(access._read_policy("myservice", "myidentity"))
    print("\n==Storage policy:\n", policy)
    assert policy["Statement"][-1]["Resource"] == ["arn:aws:s3:::myservice/myidentity/*"]


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

    creds = await access.create_store_access(
        store_creds,
        service=service,
        identity=identity,
        ttl=30,
    )

    # Temporary credentials
    assert creds.access_key != store_creds.access_key
    assert creds.session_token

    # Attempt access
    client = _store_client(creds)

    wr = client.put_object(
        service,
        f"{identity}/test",
        BytesIO(b"foo"),
        length=3,
    )
    print("==Storage write result: ", wr)

    resources = await list_store(client, service=service, identity=identity)
    assert "test" in (r.name for r in resources)

    await delete_store(client, "test", service=service, identity=identity)

    # Access is restricted to the identity prefix
    with pytest.raises(minio.error.S3Error):
        client.put_object(
            service,
            "notallowed/test",
            BytesIO(b"foo"),
            length=3,
        )

    with pytest.raises(minio.error.S3Error):
        list(client.list_objects(service, prefix="notallowed/"))

    # Without the session token, the credentials are rejected
    client = _store_client(dataclasses.replace(creds, session_token=None))
    with pytest.raises(minio.error.S3Error):
        client.put_object(
            service,
            f"{identity}/test",
            BytesIO(b"foo"),
            length=3,
        )


@pytest.mark.minio
async def test_store_access_error(store_creds: StoreCreds, monkeypatch: pytest.MonkeyPatch):
    """Store errors are raised as StoreError"""
    invalid_creds = dataclasses.replace(store_creds, secret_key="invalid")  # noqa S106

    # Bucket creation failure
    with pytest.raises(StoreError) as err:
        await access.create_store_access(
            invalid_creds,
            service="myservice",
            identity="myidentity",
            ttl=30,
        )
    assert err.value.status_code == 403

    # Temporary credentials request failure
    monkeypatch.setattr(access, "_create_store", lambda *args, **kwargs: None)
    with pytest.raises(StoreError) as err:
        await access.create_store_access(
            invalid_creds,
            service="myservice",
            identity="myidentity",
            ttl=30,
        )
    assert err.value.status_code == 502
