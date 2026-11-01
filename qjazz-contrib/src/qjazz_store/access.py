import asyncio
import dataclasses
import json
import os

from importlib import resources
from string import Template
from typing import Optional

import certifi
import urllib3

from minio.credentials import AssumeRoleProvider

from .store import (
    StoreCreds,
    StoreError,
    _create_store,
    store_client,
    store_error,
)

# Minimum duration of STS credentials
MIN_ACCESS_TTL = 900


def _read_policy(service: str, identity: str) -> str:
    """Read policy template for identity"""
    template_file = resources.files("qjazz_store").joinpath(  # type: ignore [call-arg]
        "templates",
        "store-policy.json",
    )

    with template_file.open() as f:
        template = f.read()

    content = Template(template).substitute(service=service, identity=identity)
    # Compact the policy: it is sent as a query parameter
    return json.dumps(json.loads(content), separators=(",", ":"))


def _http_client(creds: StoreCreds) -> urllib3.PoolManager:
    # Same TLS settings as the Minio client
    if creds.cert_check:
        return urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=os.environ.get("SSL_CERT_FILE") or certifi.where(),
        )
    return urllib3.PoolManager(cert_reqs="CERT_NONE")


def _setup_store(
    creds: StoreCreds,
    *,
    service: str,
    identity: str,
    ttl: int,
    location: Optional[str] = None,
) -> StoreCreds:
    """Setup a store for identity

    Create a bucket 'service/' and return temporary
    credentials restricted to the 'service/identity/' prefix.
    """
    # Do not forget to define SSL_CERT_FILE environment variable to point
    # to the CA file
    with store_error():
        _create_store(store_client(creds), service=service, location=location)

    # Request temporary credentials with an inline session policy
    # (STS AssumeRole): the effective permissions are the intersection
    # of the policy and the permissions of the admin credentials.
    # Note: the backend may cap the duration (e.g. 12h for RustFS and AWS)
    scheme = "https" if creds.secure else "http"
    provider = AssumeRoleProvider(
        f"{scheme}://{creds.endpoint}",
        access_key=creds.access_key,
        secret_key=creds.secret_key,
        duration_seconds=max(ttl, MIN_ACCESS_TTL),
        policy=_read_policy(service, identity),
        region=creds.region,
        http_client=_http_client(creds),
    )
    try:
        temp = provider.retrieve()
    except ValueError as err:
        # Raised by minio on HTTP error
        raise StoreError(status=502, message=f"Failed to create store access: {err}") from None

    return dataclasses.replace(
        creds,
        access_key=temp.access_key,
        secret_key=temp.secret_key,
        session_token=temp.session_token,
    )


async def create_store_access(
    creds: StoreCreds,
    *,
    service: str,
    identity: str,
    ttl: int,
) -> StoreCreds:
    """Create a store access

    Returns temporary credentials restricted to the identity
    prefix in the service bucket and valid for the 'ttl' duration
    in seconds (minimum 900s).
    """
    return await asyncio.to_thread(
        _setup_store,
        creds,
        service=service,
        identity=identity,
        ttl=ttl,
        location=creds.region,
    )
