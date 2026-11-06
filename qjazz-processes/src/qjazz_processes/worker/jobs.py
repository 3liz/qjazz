
from string import Template

from qjazz_core.config import (
    AbsoluteDirectoryPath,
    ConfigBase,
    TemplateStr,
)
from qjazz_core.models import Field


class JobConfig(ConfigBase):

    store_url: TemplateStr = Field(
        default=Template("${public_url}/jobs/$jobId/files/$resource"),
        validate_default=True,
        title="Public download url",
        description="""
        Url template for downloading resources.
        This is the public base url that will be seen in
        referenced responses.
        This url will need to be translated by the front end
        executor to an effective download url.
        """,
    )

    workdir: AbsoluteDirectoryPath = Field(
        title="Working directory",
        description="""
        Parent working directory where processes are executed.
        Each job will create a working directory for storing
        result files and logs.
        """,
    )

