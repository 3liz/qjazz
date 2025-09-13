#
# Http callback
#
from importlib.metadata import version
from typing import (
    Optional,
    Sequence,
    cast,
)

import requests

from pydantic import (
    AnyHttpUrl,
    FilePath,
    PositiveInt,
    TypeAdapter,
)
from qjazz_core import logger
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field, Option

from ..accesscontrol import AccessControlConfig
from ..callbacks import CallbackHandler, JobResults, Url


class HttpCallbackConfig(ConfigBase):
    ca_cert: Option[FilePath] = Field(
        title="Path to CA file",
    )
    user_agent: str = Field(
        default=f"Qjazz processes v{version('qjazz_processes')}",
        title="User agent",
    )
    timeout: PositiveInt = Field(
        default=5,
        title="Request timeout",
        description="""
        The request timeout value for both connect and read timeout.
        """,
    )

    acl: AccessControlConfig = Field(AccessControlConfig())


class HttpCallback(CallbackHandler):
    Config = HttpCallbackConfig

    def __init__(self, schemes: Sequence[str], conf: HttpCallbackConfig):
        for s in schemes:
            if s not in ("http", "https"):
                raise ValueError("Http callback: unsupported scheme '%s'", s)

        self._conf = conf

    #
    # Callback protocol implementation
    #

    def on_success(self, url: Url, job_id: str, _, results: JobResults):
        self.send_request(url, job_id, results)

    def on_failure(self, url: Url, job_id: str, _):
        self.send_request(url, job_id)

    def in_progress(self, url: Url, job_id: str, _):
        self.send_request(url, job_id)

    def send_request(
        self,
        url: Url,
        job_id: str,
        data: Optional[JobResults] = None,
    ) -> requests.Response:
        _ = TypeAdapter(AnyHttpUrl).validate_python(url.geturl())

        if not self._conf.acl.check_hostname(cast("str", url.hostname)):
            raise ValueError("Host not allowed in HTTP callback: %s", url.hostname)

        headers = {
            "x-job-id": job_id,
            "user-agent": self._conf.user_agent,
        }

        urlstr = url.geturl().format(job_id=job_id)

        kwargs: dict = {}
        if self._conf.ca_cert:
            kwargs.update(verify=str(self._conf.ca_cert))

        # Execute POST
        logger.debug("Sending HTTP callback to %s", urlstr)
        resp = requests.post(
            urlstr,
            json=data,
            headers=headers,
            timeout=self._conf.timeout,
            **kwargs,
        )
        if resp.status_code > 299:
            logger.error(
                "Callback request returned code %s: %s",
                resp.status_code,
                resp.text,
            )

        return resp


def dump_toml_schema() -> None:
    from ..doc import dump_callback_config_schema

    dump_callback_config_schema("https", "qjazz_processes.callbacks.Http", HttpCallbackConfig)


if __name__ == "__main__":
    dump_toml_schema()
