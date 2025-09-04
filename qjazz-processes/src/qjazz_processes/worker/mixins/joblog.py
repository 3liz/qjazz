from pathlib import Path
from time import time
from typing import (
    Protocol,
    cast,
)

from celery.worker.control import inspect_command

from qjazz_contrib.core.utils import to_utc_datetime

from ..models import ProcessLogVersion


class JoblogProto(Protocol):
    _workdir: Path

    def job_log(self, job_id: str) -> ProcessLogVersion: ...


@inspect_command(
    args=[("job_id", str)],
)
def job_log(state, job_id):
    """Return job log"""
    app = cast(JoblogProto, state.consumer.app)
    return app.job_log(job_id).model_dump()


class JoblogMixin(JoblogProto):
    def job_log(self, job_id: str) -> ProcessLogVersion:
        """Return job log"""
        logfile = self._workdir.joinpath(job_id, "processing.log")
        if not logfile.exists():
            text = "No log available"
        else:
            with logfile.open() as f:
                text = f.read()

        return ProcessLogVersion(timestamp=to_utc_datetime(time()), log=text)
