#
# Processing worker
#

from pydantic import Field

from py_qgis_contrib.core.config import (
    section,
)

# Re-export
from ._celery import CeleryConfig

#
# Worker configuration
#


@section('worker', field=...)
class WorkerConfig(CeleryConfig):
    service_name: str = Field(
        title="Name of the service",
        description=(
            "Name used as location service name\n"
            "for initializing Celery worker."
        ),
    )
