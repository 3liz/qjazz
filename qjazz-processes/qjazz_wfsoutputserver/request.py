import os
import traceback

from collections.abc import Sequence
from pathlib import Path
from typing import (
    Iterator,
    Literal,
    Optional,
)

from pydantic import PositiveInt

from qgis.core import QgsProcessingFeedback, QgsProject
from qgis.server import (
    QgsServer,
    QgsServerRequest,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_postcondition
from qjazz_processes.processing.prelude import (
    ProcessingContext,
)
from qjazz_processes.schemas import (
    Field,
    JsonModel,
    Option,
    RunProcessException,
)
from qjazz_processes.schemas.bbox import BboxCoordinates

from .file import QgsServerFileResponse
from .formats import WfsOutputFormat

#
# WFS Output parameters
#

OWS_WFS_VERSION = "1.1.0"


class WfsOutputParameters(JsonModel):
    layer: str = Field(
        title="Layer",
        description="""Specifiy the layer to get features from""",
        pattern="^[^,]+$",  # Exclude comma from name which will be seen as a separator
    )
    propertyname: Option[str] = Field(title="Property", description="Specify a property to return.")
    maxfeatures: Option[PositiveInt] = Field(
        title="Feature limit",
        description="Max number of features returned",
    )
    startindex: Option[PositiveInt] = Field(
        title="Paging index",
    )
    srsname: Option[str] = Field(
        title="Output SRS",
    )
    bbox: Option[BboxCoordinates] = Field(
        title="Map extent",
    )
    filter: Option[str] = Field(
        title="OGC Filter",
        description="""
        Allows to filter the response with the `Filter Encoding language`
        defined by the OGC Filter Encoding standard.
        """,
    )
    sort_by: Option[str] = Field(
        title="Sort by",
        description="Property name to sort by",
    )
    sort_order: Literal["ascending", "descending"] = Field(
        default="ascending",
        title="Sort order",
    )
    geometryname: Option[str] = Field(
        title="Geometry type",
    )
    exp_filter: Sequence[str] = Field(
        [],
        title="QGIS expression filters",
    )
    name: Option[str] = Field(
        title="Output name",
        description="""
        A custom output name identifier.
        This identifier will be used as basename
        for the generated files.
        The identitfier must be a letter followed by
        letters, digits and may include underscore or
        ascii dash (-).
        """,
        pattern="^[a-zA-Z][a-zA-Z0-9_-]+$",
    )

    # Transform parameters to GETFEATURE request parameters
    def to_query_params(self) -> Iterator[tuple[str, str]]:
        for name, val in self.model_dump().items():
            if val is None:
                continue
            match name:
                case "name":
                    continue  # Not a parameter
                case "layer":
                    name = "typename"
                case "bbox":
                    val = ",".join(val)
                case "sort_order":
                    continue
                case "sort_by":
                    name = "sortby"
                    if self.sort_order == "ascending":
                        val = f"{val} A"
                    else:
                        val = f"{val} D"
                case "exp_filter":
                    val = ";".join(val)

            if val:
                yield (name.upper(), str(val))

    def query(
        self,
        output_format: WfsOutputFormat,
    ) -> Iterator[tuple[str, str]]:
        if output_format.value.is_native():
            OUTPUTFORMAT = output_format.value.media_type
        else:
            OUTPUTFORMAT = "GML2"

        yield "SERVICE", "WFS"
        yield "REQUEST", "GetFeature"
        yield "VERSION", OWS_WFS_VERSION
        yield "OUTPUTFORMAT", OUTPUTFORMAT
        yield from self.to_query_params()


#
# GetFeture Request
#


def getfeature_request(
    basename: str,
    feedback: QgsProcessingFeedback,
    context: ProcessingContext,
    server: QgsServer,
    project: QgsProject,
    query: str,
    output_format: WfsOutputFormat,
) -> Path:
    is_native = output_format.value.is_native()

    output_file = context.workdir.joinpath(basename)
    if is_native:
        output_file = output_file.with_suffix(output_format.value.suffix)
    else:
        output_file = output_file.with_suffix(".gml")

    logger.info("Executing GetFeature request: %s", query)

    req = QgsServerRequest(f"?{query}", QgsServerRequest.GetMethod)
    response = QgsServerFileResponse(output_file)
    server.handleRequest(req, response, project=project)

    response.flush()

    status_code = response.statusCode()
    if status_code != 200:
        logger.error(
            "Feature request returned code %s: \n%s",
            status_code,
            head_file_content(output_file),
        )
        raise RunProcessException("GetFeature request failed (code: %s)", status_code)

    assert_postcondition(output_file.exists())
    return output_file


def download_xsd(
    basename: str,
    layer: str,
    feedback: QgsProcessingFeedback,
    context: ProcessingContext,
    server: QgsServer,
    project: QgsProject,
) -> Optional[Path]:
    output_file = context.workdir.joinpath(basename).with_suffix(".xsd")
    logger.info("Downloading XSD file")

    query = {
        "SERVICE": "WFS",
        "VERSION": "1.0.0",
        "REQUEST": "DescribeFeatureType",
        "OUTPUT": "XMLSCHEMA",
    }

    qs = "&".join(f"{k}={v}" for k, v in query.items())

    req = QgsServerRequest(f"?{qs}", QgsServerRequest.GetMethod)
    response = QgsServerFileResponse(output_file)
    server.handleRequest(req, response, project=project)

    response.flush()

    status_code = response.statusCode()
    if status_code != 200:
        os.rename(output_file, f"{output_file}.err")
        logger.error(
            "XSD request returned code %s: \n%s",
            status_code,
            head_file_content(output_file),
        )
        return None
    else:
        return output_file


def head_file_content(file: Path) -> str:
    if file.exists():
        try:
            return file.open().read(512)
        except Exception:
            logger.critical(traceback.format_exc())
    return "<No data>"
