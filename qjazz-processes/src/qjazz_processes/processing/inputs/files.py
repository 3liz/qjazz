import base64
import mimetypes

from pathlib import Path
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Optional,
    TypeAlias,
    Union,
    assert_never,
    cast,
)

import requests

from pydantic import JsonValue
from qjazz_core import logger

from qgis.core import Qgis, QgsProject

from qjazz_processes.schemas import (
    Formats,
    InputValueError,
    LinkReference,
    MediaType,
    Metadata,
    MetadataValue,
    OneOf,
    OutputFormatDefinition,
    QualifiedInputValue,
    RefOrQualifiedInput,
    ValuePassing,
)

from ..config import ProcessingConfig
from ..utils import (
    normalize_path,
    output_file_formats,
    resolve_raw_path,
    resolve_raw_reference,
)
from .base import (
    InputParameter,
    ProcessingContext,
)

if TYPE_CHECKING:
    from qgis.core import (
        QgsProcessingParameterFile,
        QgsProcessingParameterFileDestination,
    )
#
# QgsProcessingParameterFile
#


class ParameterFile(InputParameter):
    def value_passing(self) -> ValuePassing:
        return ("byValue", "byReference")

    @classmethod
    def create_model(
        cls,
        param: "QgsProcessingParameterFile",
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        #
        # Input data may be reference or
        # inline data
        #
        # Schema for Reference data is given by LinkReference
        # schema.
        #
        _type: Any = str
        if param.behavior() == Qgis.ProcessingFileParameterBehavior.Folder:
            logger.warning("Folder behavior not allowed for %s", param.name())
            return _type

        ext = file_extension(param)
        media_type = mimetypes.types_map.get(ext, Formats.ANY.media_type)

        return OneOf[  # type: ignore [misc, valid-type]
            Union[
                MediaType(str, media_type),
                LinkReference,
            ],
        ]

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> str:
        param = self._param

        if param.behavior() == Qgis.ProcessingFileParameterBehavior.Folder:
            # XXX Passing a folder is not really relevant for processes API
            # except if we allow raw input value
            if context and context.config.raw_destination_input_sink:
                return str(
                    resolve_raw_path(
                        cast("str", inp),
                        context.workdir,
                        context.config.raw_destination_root_path,
                        "",
                    ),
                )
            logger.warning("Folder behavior not allowed for %s", param.name())
            return ""

        if context and context.config.raw_destination_input_sink:
            #
            # Allow referencing a file system resource
            #
            _inp = cast("dict", inp)
            p = resolve_raw_reference(
                cast("str", _inp.get("href", "")),
                context.workdir,
                context.config.raw_destination_root_path,
                file_extension(param),
            )
            if p:
                if not p.exists():
                    raise InputValueError(f"{param.name()}: file not found '{p}'")
                return str(p)

        _inp = RefOrQualifiedInput.validate_python(inp)

        workdir = (context and context.workdir) or Path()
        destination = workdir.joinpath(param.name()).with_suffix(file_extension(param))

        try:
            value: Any  # Makes Mypy happy

            with destination.open("wb") as out:
                match _inp:
                    case QualifiedInputValue():
                        value = _inp.value
                        if _inp.encoding in ("base64", "binary"):
                            value = base64.b64decode(value)
                            out.write(value)
                        else:
                            out.write(value.encode())
                    case LinkReference():
                        download_ref(_inp, context.config if context else None, out)
                    case _ as unreachable:
                        # XXX should never happen
                        assert_never(unreachable)  # type: ignore [arg-type]

            return str(destination)
        except:
            if destination.exists():
                destination.unlink()
            raise


#
# QgsProcessingParameterFileDestination
#


class ParameterFileDestination(InputParameter, OutputFormatDefinition):
    _ParameterType = str

    def initialize(self):
        ext = self._param.defaultFileExtension()
        if ext and ext != "file":
            self.output_extension = f".{ext}"

    @classmethod
    def metadata(cls, param: "QgsProcessingParameterFileDestination") -> list[Metadata]:
        md = super(ParameterFileDestination, cls).metadata(param)

        formats = output_file_formats(param)
        if formats:
            md.append(
                MetadataValue(
                    role="outputFormats",
                    value=[mt.media_type for mt in formats],
                ),
            )
        return md

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> str:
        path = resolve_path(self, inp, context or ProcessingContext())

        ext = self.output_extension
        if ext:
            path = path.with_suffix(ext)
        return str(path)


#
# QgsProcessingParameterFolderDestination
#


class ParameterFolderDestination(InputParameter):
    _ParameterType = str

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> str:
        return str(resolve_path(self, inp, context or ProcessingContext()))

#
# Utils
#


def file_extension(param: "QgsProcessingParameterFile") -> str:
    """Return the file parameter extension with a leading dot

    QGIS expects the extension without leading dot (i.e 'csv')
    but accept both forms.
    """
    ext = param.extension().strip()
    return f".{ext}" if (ext and not ext.startswith(".")) else ext


def resolve_path(self: InputParameter, inp: JsonValue, context: ProcessingContext) -> Path:
    _inp = self.validate(inp)

    if context.config.raw_destination_input_sink:
        value = resolve_raw_path(
            _inp,
            context.workdir,
            context.config.raw_destination_root_path,
            "",
        )
    else:
        # Normalize path
        workdir = normalize_path(context.workdir)
        value = normalize_path(workdir.joinpath(_inp.removeprefix("/")))
        if not value.is_relative_to(workdir):
            # Truncate the path to its single name
            value = workdir.joinpath(value.name)
            logger.warning(
                "Value for '%s' has been truncated to '%s'",
                self._param.name(),
                value,
            )

    return value


def download_ref(ref: LinkReference, config: Optional[ProcessingConfig], writer: IO):
    """Download reference"""
    method = ref.method or "GET"
    href = str(ref.href)

    logger.info("Downloading reference from %s (%s)", href, method)

    headers = {}
    if ref.mime_type:
        headers["Accept"] = ref.mime_type

    if ref.hreflang:
        headers["Accept-Language"] = ref.hreflang

    kwargs: dict = {}
    if ref.body:
        kwargs.update(data=ref.body)

    if config:
        timeout = config.download_timeout
        ssl = config.certificats
        if ssl.cafile:
            kwargs.update(verify=str(ssl.cafile))
        if ssl.keyfile and ssl.certfile:
            kwargs.update(cert=(str(ssl.certfile), str(ssl.keyfile)))
    else:
        timeout = 20.0

    resp = requests.request(method, href, headers=headers, stream=True, timeout=timeout, **kwargs)
    if resp.status_code not in (200, 206):
        raise InputValueError(f"Reference request error: ({resp.status_code}) {resp.text}")

    part_size = 1024 * 64

    writer.writelines(resp.iter_content(chunk_size=part_size))
