import asyncio
import os
import secrets
import traceback

from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from pathlib import Path
from string import Template
from tempfile import NamedTemporaryFile, gettempdir
from time import time
from typing import Generator, Optional, TypeAlias

from minio import Minio, MinioAdmin, credentials

from qjazz_core import logger
from qjazz_core.utils import to_iso8601

from .store import (
    StoreCreds,
    _create_store,
)

StoreClient: TypeAlias = Minio


def _passgen(nchars: int) -> str:
    return secrets.token_hex(nchars // 2)


STORE_TMPDIR_VAR = "QJAZZ_STORE_TMPDIR"


@contextmanager
def _read_policy(service: str, identity: str) -> Generator[Path, None, None]:
    """Read policy template for identity"""
    tmpdir = Path(os.getenv(STORE_TMPDIR_VAR, gettempdir()))
    template_file = resources.files("qjazz_store").joinpath(  # type: ignore [call-arg]
        "templates",
        "store-policy.json",
    )

    with template_file.open() as f:
        template = f.read()

    content = Template(template).substitute(service=service, identity=identity)
    # XXX with 3.12+ use delete_on_close=True
    with NamedTemporaryFile(mode="w", suffix=".json", dir=tmpdir, delete=False) as dest:
        dest.write(content)
        dest.close()
        path = Path(dest.name)
        try:
            yield path
        finally:
            path.unlink()


def _setup_store(
    creds: StoreCreds,
    *,
    service: str,
    identity: str,
    ttl: int,
    location: Optional[str] = None,
) -> tuple[str, str, str]:
    """Setup a minio store for identity

    Create a bucket 'service/'
    """
    # Do not forget to define SSL_CERT_FILE environment variable to point
    # to the CA file
    m: Minio | MinioAdmin
    m = Minio(
        creds.endpoint,
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        secure=creds.secure,
        cert_check=creds.cert_check,
    )
    # Create the bucket for the service
    _create_store(m, service=service, location=location)

    # Create the service account: (threaded)
    # Read policy template
    with _read_policy(service, identity) as policy:
        m = MinioAdmin(
            creds.endpoint,
            credentials=credentials.StaticProvider(
                access_key=creds.access_key,
                secret_key=creds.secret_key,
            ),
            secure=creds.secure,
            cert_check=creds.cert_check,
        )
        # Minio access_key length must be < 20
        accnt_access_key = _passgen(20)
        accnt_secret_key = _passgen(40)

        # Minio require 15mn minimum expiration ttl
        # XXX: Minio server return 500 if given an invalid date
        expiration = to_iso8601(datetime.fromtimestamp(time() + max(ttl, 960)), timespec="seconds")

        # Create service account
        m.add_service_account(
            access_key=accnt_access_key,
            secret_key=accnt_secret_key,
            # XXX Rule for service account name format is somewhat obscure....
            # name=identity,
            description=f"Store account for {service}/{identity}",
            expiration=expiration,
            policy_file=str(policy),
        )
        return (accnt_access_key, accnt_secret_key, expiration)


def _delete_store_access(
    creds: StoreCreds,
    *,
    account: str,
):
    m = MinioAdmin(
        creds.endpoint,
        credentials=credentials.StaticProvider(
            access_key=creds.access_key,
            secret_key=creds.secret_key,
        ),
        secure=creds.secure,
        cert_check=creds.cert_check,
    )
    try:
        m.delete_service_account(account)
    except Exception:
        logger.error(
            "Delete store acces error for %s:\n%s",
            creds.access_key,
            traceback.format_exc(),
        )


async def delete_store_access(
    creds: StoreCreds,
    *,
    account: str,
    endpoint: str,
):
    await asyncio.to_thread(_delete_store_access, creds, account=account)


async def create_store_access(
    creds: StoreCreds,
    *,
    service: str,
    identity: str,
    ttl: int,
) -> tuple[str, str, str]:
    """Create a store access key

    Returns a wrapped data token with 'access_key' and 'secret_key'
    valid for the 'ttl' duration is seconds
    """
    return await asyncio.to_thread(
        _setup_store,
        creds,
        service=service,
        identity=identity,
        ttl=ttl,
        location=creds.region,
    )
