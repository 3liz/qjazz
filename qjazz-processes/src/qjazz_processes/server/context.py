import dataclasses

from pydantic import JsonValue
from qjazz_store import StoreCreds
from qjazz_store.access import create_store_access

from .executor import ProcessSummary


async def update_store_context(
    context: dict[str, JsonValue],
    process: ProcessSummary,
    service: str,
    identity: str,
    creds: StoreCreds,
    ttl: int,
):
    (access_key, secret_key, _) = await create_store_access(
        creds,
        service=service,
        identity=identity,
        ttl=ttl,
    )

    context.update(
        store_creds=dataclasses.asdict(
            dataclasses.replace(
                creds,
                access_key=access_key,
                secret_key=secret_key,
            ),
        ),
    )
