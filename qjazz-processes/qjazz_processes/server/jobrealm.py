#
# Handle job realm
#
from typing import Annotated, Optional, Sequence
from uuid import uuid4

from aiohttp import web
from pydantic import Field, TypeAdapter, ValidationError

from qjazz_contrib.core.config import ConfigBase, section

from .models import ErrorResponse

JOB_REALM_HEADER = "X-Job-Realm"


RealmToken: TypeAdapter = TypeAdapter(
    Annotated[
        str,
        Field(min_length=8, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-]+$"),
    ],
)


@section("job_realm")
class JobRealmConfig(ConfigBase):
    """
    Defining job realm allow filtering job's requests by a token that is
    set by the client when requesting task execution (see description below).
    """

    enabled: bool = Field(
        default=False,
        title="Enable job realm header",
        description=(
            f"When enabled, use the '{JOB_REALM_HEADER}' http header\n"
            "as a client identification token for retrieving jobs status and results."
        ),
    )
    admin_tokens: Sequence[str] = Field(
        default=(),
        title="Admininistrator realm jobs tokens",
        description=("Define catch all tokens for listing and retrieve status and results\nfor all jobs."),
    )

    def validate_realm(self, realm: str) -> str:
        try:
            return RealmToken.validate_python(realm)
        except ValidationError:
            ErrorResponse.raises(web.HTTPUnauthorized, "Invalid job realm")

    def get_job_realm(self, request: web.Request) -> Optional[str]:
        """Return a job realm either from the headers
        or create a new one
        """
        if self.enabled:
            realm = request.headers.get(JOB_REALM_HEADER)
            realm = self.validate_realm(realm) if realm else str(uuid4())
            return realm
        else:
            return None

    def job_realm(self, request: web.Request) -> Optional[str]:
        """Return job realm from headers

        Return Unauthorized if job realm is requested
        """
        if self.enabled:
            realm = request.get(JOB_REALM_HEADER)
            if not realm:
                raise ErrorResponse.raises(web.HTTPUnauthorized, "Unauthorized")
            if realm in self.admin_tokens:
                realm = None
        else:
            realm = None
        return realm
