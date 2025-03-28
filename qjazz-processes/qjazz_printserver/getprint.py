from collections.abc import Sequence
from typing import (
    Annotated,
    Iterator,
    Literal,
    Optional,
    cast,
)
from urllib.parse import urlencode

from pydantic import TypeAdapter, alias_generators
from pydantic.aliases import PydanticUndefined

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingFeedback,
    QgsProject,
)
from qgis.server import (
    QgsServer,
    QgsServerProjectUtils,
    QgsServerRequest,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_processes.processing.prelude import (
    ProcessingContext,
)
from qjazz_processes.schemas import (
    Field,
    Format,
    InputDescription,
    InputValueError,
    JobExecute,
    JobResults,
    Link,
    MetadataValue,
    OutputDescription,
    ProcessDescription,
    ProcessSummary,
    RunProcessException,
)

from .composers import (
    Composer,
    get_composers,
    get_map_layout_items_for,
)
from .file import QgsServerFileResponse
from .models import model_description
from .parameters import GetPrintParameters, MapOptions


def get_wms_layers(project: QgsProject) -> Iterator[str]:
    restricted_layers = set(QgsServerProjectUtils.wmsRestrictedLayers(project))
    use_layer_ids = QgsServerProjectUtils.wmsUseLayerIds(project)
    for layer in project.mapLayers().values():
        if layer.name() in restricted_layers:
            continue
        if use_layer_ids:
            yield layer.id()
        else:
            if Qgis.QGIS_VERSION_INT < 33800:
                name = layer.shortName()
            else:
                name = layer.serverProperties().shortName()
            if not name:
                name = layer.name()
            yield name


def get_print_templates(project: QgsProject) -> Sequence[str]:
    restricted_composers = set(QgsServerProjectUtils.wmsRestrictedComposers(project))
    manager = project.layoutManager()
    return tuple(layout.name() for layout in manager.printLayouts()
        if layout.name() not in restricted_composers)


def get_advertised_crss(project: QgsProject) -> Sequence[str]:
    crss = tuple(crs for crs in QgsServerProjectUtils.wmsOutputCrsList(project))
    if not crss:
        crs = project.crs()
        if crs.isValid():
            crss = (crs.authid(),)
        else:
            crss = ("OGC:CRS84",)
    return crss


ComposerListA: TypeAdapter = TypeAdapter(Sequence[Composer])

#
# GetPrint Process
#

OWS_GETPRINT_VERSION = "1.3.0"


class GetPrintProcess:
    @classmethod
    def inputs(
        cls,
        project: Optional[QgsProject] = None,
    ) -> Iterator[tuple[str, InputDescription]]:
        """Convert fields to InputDescription"""
        for name, field in GetPrintParameters.model_fields.items():
            type_: object
            default = field.default
            match name:
                case "template" if project:
                    type_ = Literal[get_print_templates(project)]  # type: ignore [misc]
                case "layers" if project:
                    type_ = Optional[set[Literal[  # type: ignore [misc]
                        tuple(get_wms_layers(project))
                    ]]]
                case "crs" if project:
                    type_ = Literal[get_advertised_crss(project)]  # type: ignore [misc]
                case _:
                    type_ = field.annotation

            if default not in (None, PydanticUndefined):
                type_ = Annotated[type_, Field(default=default)]

            yield (
                alias_generators.to_camel(name),
                model_description(
                    type_,
                    optional=not field.is_required(),
                    title=field.title,
                    description=field.description,
                    schema_extra=field.json_schema_extra,
                ),
            )

    output_formats: Sequence[Format] = (
        Format("application/pdf", ".pdf", "Document PDF"),
        Format("image/png", ".png", "Image PNG"),
        Format("image/jpeg", ".jpg", "Image JPEG"),
        Format("image/svg+xml", ".svg", "Image SVG"),
    )

    _output_description: OutputDescription | None = None

    @classmethod
    def output(cls) -> OutputDescription:
        """Return output parameter description"""
        if not cls._output_description:
            schema = Link.model_json_schema()

            cls._output_description = OutputDescription(
                title="Output format",
                description="Select the output document format",
                value_passing=("byReference",),
                schema={
                    "$defs": {"Link": schema},
                    "anyOf": [
                        {
                            "$ref": "#/$defs/Link",
                            "contentMediaType": fmt.media_type,
                            "title": fmt.title,
                        }
                        for fmt in cls.output_formats
                    ],
                },
            )

        return cast(OutputDescription, cls._output_description)

    process_id = "getprint"

    _version_info = (1, 0)

    @classmethod
    def _description(cls, project: Optional[QgsProject] = None) -> ProcessDescription:
        description = ProcessDescription(
            id_=cls.process_id,  # type: ignore [call-arg]
            title="GetPrint",
            description="Create print layout document.",
            version=".".join(str(n) for n in cls._version_info),
        )

        # Update metadata
        description.metadata = [
            MetadataValue(role="QgisVersion", title="Qgis version", value=Qgis.version()),
            MetadataValue(
                role="QgisVersionInt",
                title="Qgis version int",
                value=Qgis.versionInt(),
            ),
            MetadataValue(role="Deprecated", title="Deprecated", value=False),
            MetadataValue(role="KnownIssues", title="Known issues", value=False),
            MetadataValue(role="RequiresProject", title="Requires project", value=True),
        ]

        if project:
            description.metadata.append(
                MetadataValue(
                    role="Templates",
                    title="Templates",
                    value=ComposerListA.dump_python(tuple(get_composers(project)), mode='json'),
                ),
            )

        return description

    @classmethod
    def summary(cls) -> ProcessSummary:
        return cls._description()

    @classmethod
    def description(cls, project: Optional[QgsProject]) -> ProcessDescription:
        return cls._description(project).model_copy(
            update=dict(
                inputs=dict(cls.inputs(project)),
                outputs={"output": cls.output()},
            ),
        )

    @classmethod
    def parameters(
        cls,
        request: JobExecute,
        params: Optional[GetPrintParameters] = None,
    ) -> Iterator[tuple[str, str]]:
        output = request.outputs.get("output")
        if not output:
            raise InputValueError("Missing output format definition")

        if output.format not in cls.output_formats:
            raise InputValueError(f"Invalid format definition: {output.format.media_type}")

        params = params or GetPrintParameters.model_validate(request.inputs)

        yield "SERVICE", "WMS"
        yield "REQUEST", "GetPrint"
        yield "VERSION", OWS_GETPRINT_VERSION
        yield "FORMAT", output.format.media_type
        yield from params.to_query_params()

    @classmethod
    def execute(
        cls,
        request: JobExecute,
        feedback: QgsProcessingFeedback,
        context: ProcessingContext,
        server: QgsServer,
    ) -> JobResults:
        """Execute GetPrint request"""
        project = context.project()
        assert_precondition(project is not None)

        params = GetPrintParameters.model_validate(request.inputs)

        output_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(params.crs)
        if not output_crs.isValid():
            raise RunProcessException(f"Invalid CRS: {params.crs}")

        # If no options are sets
        # we need to pass the extent
        map_items = get_map_layout_items_for(project, params.template, output_crs)
        if not params.map_options:
            params.map_options = {m.ident: MapOptions(extent=m.extent) for m in map_items}
        else:
            for m in get_map_layout_items_for(project, params.template, output_crs):
                opts = params.map_options[m.ident]
                if opts and not opts.extent:
                    opts.extent = m.extent

        _query = urlencode(tuple(cls.parameters(request, params)))

        def find_format() -> Format:
            of = request.outputs["output"].format
            for f in cls.output_formats:
                if f == of:
                    return f
            raise RunProcessException(f"Unexpected output format: {of}")

        output_format = find_format()
        output_file = context.workdir.joinpath(f"getprint-{context.job_id}{output_format.suffix}")

        with params.set_custom_variables(project):
            logger.debug("Executing getprint request: %s", _query)

            req = QgsServerRequest(f"?{_query}", QgsServerRequest.GetMethod)
            response = QgsServerFileResponse(output_file)
            server.handleRequest(req, response, project=project)

        status_code = response.statusCode()
        if status_code != 200:
            raise RunProcessException(f"Getprint failure (code: {status_code})")

        reference = context.file_reference(output_file)

        return {
            "output": Link(
                href=reference,
                mime_type=output_format.media_type,
                title="GetPrint document",
                length=output_file.stat().st_size,
            ).model_dump(mode="json", by_alias=True, exclude_none=True),
        }
