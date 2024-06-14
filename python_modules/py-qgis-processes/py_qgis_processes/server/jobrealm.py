#
# Handle job realm
#
from uuid import uuid4

from aiohttp import web
from pydantic import Field, TypeAdapter, ValidationError
from typing_extensions import Annotated, Optional

from py_qgis_contrib.core.config import ConfigBase, confservice, section

from .models import ErrorResponse

JOB_REALM_HEADER = 'X-Py-Qgis-Job-Realm'


@section("job_realm")
class JobRealmConfig(ConfigBase):
    (
        "Defining job realm allow filtering job's requests by a token that is\n"
        "set by the client when requesting task execution (see description below)."
    )
    enabled: bool = Field(
        default=False,
        title="Enable job realm header",
        description=(
            f"When enabled, use the '{JOB_REALM_HEADER}' http header\n"
            "as a client identification token for retrieving jobs status and results."
        ),
    )
    admin:  Optional[str] = Field(
        default=None,
        title="Admininistrator realm jobs token",
        description=(
            "A catch all token for listing and retrieve status and results\n"
            "for all jobs."
        ),
    )


RealmToken = TypeAdapter(
    Annotated[
       str,
       Field(min_length=8, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-]+$"),
    ],
)


def validate_realm(realm: str) -> str:
    try:
        return RealmToken.validate_python(realm)
    except ValidationError:
        ErrorResponse.raises(web.HTTPUnauthorized, "Invalid job realm")


def get_job_realm(request: web.Request) -> Optional[str]:
    """ Return a job realm either from the headers
        or create a new one
    """
    if confservice.conf.job_realm.enabled:
        realm = request.headers.get(JOB_REALM_HEADER)
        realm = validate_realm(realm) if realm else str(uuid4())
        return realm
    else:
        return None


def job_realm(request: web.Request) -> Optional[str]:
    """ Return job realm from headers

        Return Unauthorized if job realm is requested
    """
    if confservice.conf.job_realm.enabled:
        realm = request.get(JOB_REALM_HEADER)
        if not realm:
            raise ErrorResponse.raises(web.HTTPUnauthorized, "Unauthorized")
    else:
        realm = None
    return realm
