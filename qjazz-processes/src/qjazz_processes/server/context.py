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
    access_creds = await create_store_access(
        creds,
        service=service,
        identity=identity,
        ttl=ttl,
    )

    context.update(store_creds=dataclasses.asdict(access_creds))
