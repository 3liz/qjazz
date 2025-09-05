#
# Test callback
#
from pydantic import TypeAdapter
from qjazz_core import logger

from ..callbacks import JobResults, Url


class TestCallback:
    def __init__(self, scheme: str):
        pass

    def on_success(self, url: Url, job_id: str, results: JobResults):
        logger.debug(
            "TestCallbackHandler::on_success[%s] %s: %s",
            job_id,
            url.geturl(),
            TypeAdapter(JobResults).dump_json(results, indent=4).decode(),
        )

    def on_failure(self, url: Url, job_id: str):
        logger.debug("TestCallbackHandler::on_failure[%s] %s", job_id, url.geturl())

    def in_progress(self, url: Url, job_id: str):
        logger.debug("TestCallbackHandler::in_progress[%s] %s", job_id, url.geturl())
