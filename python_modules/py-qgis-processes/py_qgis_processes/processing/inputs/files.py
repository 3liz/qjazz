
import base64
import mimetypes

from pathlib import Path

import requests

from pydantic import JsonValue
from typing_extensions import (
    IO,
    Any,
    Dict,
    Optional,
    Type,
    Union,
    cast,
)

from qgis.core import (
    QgsProcessingContext,
    QgsProject,
)

from py_qgis_contrib.core import logger
from py_qgis_processes_schemas import (
    Formats,
    InputValueError,
    LinkReference,
    MediaType,
    OneOf,
    QualifiedInputValue,
    RefOrQualifiedInput,
)
from py_qgis_processes_schemas.processes import ValuePassing

from ..utils import (
    ProcessingFileParameterBehavior,
)
from .base import (
    InputParameter,
    ParameterDefinition,
    ProcessingConfig,
)

#
# QgsProcessingParameterFile
#


class ParameterFile(InputParameter):

    def value_passing(self) -> ValuePassing:
        return ('byValue', 'byReference')

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        #
        # Input data may be reference or
        # inline data
        #
        # Schema for Reference data is given by LinReference
        # schema.
        #
        _type: Any = str
        if param.behavior() == ProcessingFileParameterBehavior.Folder:
            logger.warning("Folder behavior not allowed for %s", param.name())
            return _type

        ext = param.extension()
        media_type = mimetypes.types_map.get(ext, Formats.ANY.media_type)

        _type = OneOf[        # type: ignore [misc, valid-type]
            Union[
                MediaType(str, media_type),
                LinkReference,
            ],
        ]

        return _type

    def value(self, inp: JsonValue, context: Optional[QgsProcessingContext] = None) -> str:

        param = self._param

        if param.behavior() == ProcessingFileParameterBehavior.Folder:
            # XXX Passing a folder is not really relevant for processes API
            # except if we allow raw input value
            if self.config.raw_destination_input_sink:
                return cast(str, inp)
            else:
                logger.warning("Folder behavior not allowed for %s", param.name())
                return ""

        _inp = RefOrQualifiedInput.validate_python(inp)

        destination = Path(param.name()).with_suffix(param.extension())

        try:
            value: Any   # Makes Mypy happy

            with destination.open('wb') as out:
                match _inp:
                    case QualifiedInputValue():
                        value = _inp.value
                        if _inp.encoding == 'base64':
                            value = base64.b64decode(value)
                        out.write(value)
                    case LinkReference():
                        download_ref(_inp, self.config, out)

            return str(destination)
        finally:
            if destination.exists():
                destination.unlink()


#
# QgsProcessingParameterFileDestination
#

class ParameterFileDestination(InputParameter):

    _ParameterType = str

    def _resolve_path(self, inp: JsonValue) -> Path:

        _inp = self.validate(inp)

        if self.config.raw_destination_input_sink:
            value = _inp
        else:
            # Normalize path
            value = Path(_inp).relative_to('/').resolve()
            if str(value) != _inp:
                logger.warning(
                    "Value for '%s' has been truncated to '%s'",
                    self._param.name(),
                    value,
                )

        return value

    def value(self, inp: JsonValue, context: Optional[QgsProcessingContext] = None) -> str:
        path = self._resolve_path(inp)

        ext = self._param.defaultFileExtension()
        if ext:
            path = path.with_suffix(f'.{ext}')
        return str(path)

#
# QgsProcessingParameterFolderDestination
#


class ParameterFolderDestination(ParameterFileDestination):

    def value(self, inp: JsonValue, context: Optional[QgsProcessingContext] = None) -> str:
        return str(self._resolve_path(inp))

#
# Utils
#


def download_ref(ref: LinkReference, config: ProcessingConfig, writer: IO):
    """ Download reference
    """
    method = ref.method or 'GET'
    href = str(ref.href)

    logger.info("Downloading reference from %s (%s)", href, method)

    headers = {}
    if ref.mime_type:
        headers['Accept'] = ref.mime_type

    if ref.hreflang:
        headers['Accept-Language'] = ref.hreflang

    kwargs: Dict = {}
    if ref.body:
        kwargs.update(data=ref.body)

    ssl = config.certificats
    if ssl.cafile:
        kwargs.update(verify=str(ssl.cafile))
    if ssl.keyfile and ssl.certfile:
        kwargs.update(cert=(str(ssl.certfile), str(ssl.keyfile)))

    resp = requests.request(method, href, headers=headers, stream=True, **kwargs)
    if resp.status_code != 200:
        raise InputValueError("Reference request error: ({resp.status_code}) {resp.text}")

    part_size = 1024 * 64

    for chunk in resp.iter_content(chunk_size=part_size):
        writer.write(chunk)
