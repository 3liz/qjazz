from collections.abc import Sequence
from textwrap import dedent as _D
from urllib.parse import urlencode

from pydantic import (
    Field,
    alias_generators,
)
from pydantic.aliases import PydanticUndefined
from typing_extensions import (
    Annotated,
    Iterable,
    Iterator,
    Literal,
    Optional,
    cast,
)

from qgis.core import Qgis, QgsProcessingFeedback, QgsProject
from qgis.server import (
    QgsServer,
    QgsServerProjectUtils,
    QgsServerRequest,
)

from qjazz_contrib.core.condition import assert_precondition
from qjazz_processes.processing.prelude import (
    ProcessingContext,
)
from qjazz_processes.schemas import (
    Format,
    InputDescription,
    InputValueError,
    JobExecute,
    JobResults,
    JsonModel,
    Link,
    MetadataValue,
    NullField,
    OutputDescription,
    ProcessDescription,
    ProcessSummary,
    RunProcessException,
)
from qjazz_processes.schemas.bbox import Extent2D

from .file import QgsServerFileResponse
from .models import model_description

# Getprint specifications
# See https://docs.qgis.org/3.34/en/docs/server_manual/services/wms.html


def _to_bool_param(b: bool) -> str:
    return "TRUE" if b else "FALSE"


def _comma_separated_list(seq: Sequence[str | int | float], sep: str = ",") -> str:
    return sep.join(str(v) for v in seq)


class PdfFormatOptions(JsonModel):
    rasterize_whole_image: Optional[bool] = NullField(
        title="Export as image",
        description="Whether the whole pdf should be exported as an image,",
    )
    force_vector_output: Optional[bool] = NullField(
        title="Export as vector",
        description="Whether pdf should be exported as vector.",
    )
    append_georeference: Optional[bool] = NullField(
        title="Add georeference",
        description="Whether georeference info shall be added to the pdf.",
    )
    export_metadata: Optional[bool] = NullField(
        title="Export metadata",
        description="Whether metadata shall be added to the pdf.",
    )
    text_render_format: Optional[Literal["AlwaysOutline", "AlwaysText"]] = Field(
        title="Text render format",
        description="Sets the text render format for pdf export",
    )
    simplify_geometry: Optional[bool] = NullField(
        title="Simplify geometries",
    )
    write_geo_pdf: Optional[bool] = NullField(
        title="Export as GeoPDF",
    )
    use_iso_32000_extension_format_georeferencing: Optional[bool] = NullField(
        title="Use Iso32000 georeferencing",
    )
    use_ogc_best_practice_format_georeferencing: Optional[bool] = NullField(
        title="Use ogc best practice georeferencing",
    )
    export_themes: Optional[str] = NullField(
        title="Exported themes",
        description="A comma separated list of map themes to use for a GeoPDF export",
    )
    predefined_map_scales: Optional[str] = NullField(
        title="Map scales",
        description="A comma separated list of map scales to render the map.",
    )
    lossless_image_compression: Optional[bool] = NullField(
        title="Use lossless compression",
        description="Whether images embedded in pdf must be compressed using a lossless algorithm.",
    )
    disable_tiled_raster_rendering: Optional[bool] = NullField(
        title="Disable raster tiling",
        description="Whether rasters shall be untiled in the pdf.",
    )

    def to_query_param(model: JsonModel) -> str:
        def _iter_values() -> Iterable[str]:
            for name, val in model.model_dump().items():
                if val is None:
                    continue
                if isinstance(val, bool):
                    val = _to_bool_param(val)

                yield f"{name.upper()}:{val}"

        return ";".join(_iter_values())


class MapOptions(JsonModel):
    extent: Optional[Extent2D] = NullField(
        title="Extent",
        description=("This parameter specifies the extent for a layout map item as [xmin,ymin,xmax,ymax]."),
    )
    rotation: Optional[float] = NullField(
        title="Rotation",
        description="This parameter specifies the map rotation in degrees.",
    )
    grid_interval_x: Optional[int] = NullField(
        title="Grid interval X",
        description="This parameter specifies the grid line density in the X direction.",
    )
    grid_interval_y: Optional[int] = NullField(
        title="Grid interval Y",
        description="This parameter specifies the grid line density in the Y direction.",
    )
    scale: Optional[float] = NullField(
        title="Scale",
        description=_D(
            """
            This parameter specifies the map scale for a layout map item.
            This is useful to ensure scale based visibility of layers and labels
            even if client and server may have different algorithms to calculate
            the scale denominator.
            """,
        ),
    )
    layers: Optional[Sequence[str]] = NullField(title="Layers")
    styles: Optional[Sequence[str]] = NullField(title="Styles")

    def to_query_params(self, name: str) -> Iterator[tuple[str, str]]:
        for field, val in self.dict().items():
            match val:
                case None:
                    continue
                case bool():
                    val = _to_bool_param(val)
                case Sequence():
                    val = _comma_separated_list(val)
                case _:
                    pass

            yield f"{name}:{field.upper()}", val


OpacityValue = Annotated[int, Field(ge=0, le=255)]
FeatureId = Annotated[int, Field(gt=0)]


#
# GetPrint Parameters
#

OWS_GETPRINT_VERSION = "1.3.0"


class GetPrintParameters(JsonModel):
    template: str = Field(
        title="Layout template",
        description="Layout template to use",
    )
    crs: str = Field(
        title="Coordinate reference system",
        description=_D(
            """
            This parameter allows to indicate the map output
            Coordinate Reference System.
            """,
        ),
    )
    format_options: Optional[PdfFormatOptions] = NullField(
        title="Pdf format options",
        description="Options for pdf output format only",
    )
    atlas_pk: Optional[str] = NullField(
        title="Atlas features",
        description=_D(
            """
            This parameter allows activation of Atlas rendering by indicating
            which features we want to print.
            In order to retrieve an atlas with all features, the * symbol
            may be used (according to the maximum number of features allowed
            in the project configuration).
            """,
        ),
    )
    styles: Optional[Sequence[str]] = NullField(
        title="Layer's style",
        description=("This parameter can be used to specify a layer's style for the rendering step."),
    )
    transparent: Optional[bool] = NullField(
        title="Transparent background",
        description="This parameter can be used to specify the background transparency.",
    )
    opacities: Optional[Sequence[OpacityValue]] = NullField(
        title="Opacity for layer or group",
        description=_D(
            """
            List of opacity values.
            Opacity can be set on layer or group level.
            Allowed values range from 0 (fully transparent) to 255 (fully opaque).
            """,
        ),
    )
    selection: Optional[dict[str, Sequence[FeatureId]]] = NullField(
        title="Highlight features",
        description=_D(
            """
            This parameter can highlight features from one or more layers.
            Vector features can be selected by passing comma separated lists
            with feature ids.
            """,
        ),
    )
    layers: Optional[Sequence[str]] = NullField(
        title="Layers to display",
        description="This parameter allows to specify the layers to display on the map.",
    )
    map_options: Optional[dict[str, MapOptions]] = NullField(
        title="Layout map item options",
        description="Allow specify layout item options",
    )

    def to_query_params(self) -> Iterator[tuple[str, str]]:
        yield "TEMPLATE", self.template
        yield "CRS", self.crs
        if self.format_options:
            yield "FORMAT_OPTIONS", self.format_options.to_query_param()
        if self.atlas_pk:
            yield "ATLAS_PK", self.atlas_pk
        if self.styles:
            yield "STYLES", _comma_separated_list(self.styles)
        if self.transparent is not None:
            yield "TRANSPARENT", _to_bool_param(self.transparent)
        if self.opacities:
            yield "OPACITIES", _comma_separated_list(self.opacities)
        if self.selection:
            val = ";".join(f"{k}:{_comma_separated_list(ids)}" for k, ids in self.selection.items())
            yield "SELECTION", val
        if self.layers:
            yield "LAYERS", _comma_separated_list(self.layers)
        if self.map_options:
            for name, opts in self.map_options.items():
                yield from opts.to_query_params(name)


def get_wms_layers(project: QgsProject) -> Sequence[str]:
    restricted_layers = set(QgsServerProjectUtils.wmsRestrictedLayers(project))
    return tuple(layer.name() for layer in project.mapLayers().values() if layer.name() not in restricted_layers)


#
# GetPrint Process
#


class GetPrintProcess:
    @classmethod
    def inputs(
        cls,
        project: Optional[QgsProject] = None,
    ) -> Iterator[tuple[str, InputDescription]]:
        """Convert fields to InputDescription"""
        for name, field in GetPrintParameters.model_fields.items():
            type_: object
            match name:
                case "layers" if project:
                    type_ = Optional[set[Literal[get_wms_layers(project)]]]  # type: ignore [misc]
                case _:
                    type_ = field.annotation

            if field.default not in (None, PydanticUndefined):
                type_ = Annotated[type_, Field(default=field.default)]

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

    _description_summary: ProcessDescription | None = None
    _version_info = (1, 0)

    @classmethod
    def _description(cls) -> ProcessDescription:
        if not cls._description_summary:
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

            cls._description_summary = description

        return cast(ProcessDescription, cls._description_summary)

    @classmethod
    def summary(cls) -> ProcessSummary:
        return cls._description()

    @classmethod
    def description(cls, project: QgsProject) -> ProcessDescription:
        return cls._description().model_copy(
            update=dict(
                inputs=dict(cls.inputs(project)),
                outputs={"output": cls.output()},
            ),
        )

    @classmethod
    def parameters(cls, request: JobExecute) -> Iterator[tuple[str, str]]:
        output = request.outputs.get("output")
        if not output:
            raise InputValueError("Missing output format definition")

        if output.format not in cls.output_formats:
            raise InputValueError(f"Invalid format definition: {output.format.media_type}")

        params = GetPrintParameters.model_validate(request.inputs)

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
        _query = urlencode(tuple(cls.parameters(request)))

        project = context.project()
        assert_precondition(project is not None)

        output_file = context.workdir.joinpath(f"getprint-{context.job_id}")

        req = QgsServerRequest(f"?{_query}", QgsServerRequest.GetMethod)
        response = QgsServerFileResponse(output_file)
        server.handleRequest(req, response, project=project)

        status_code = response.statusCode()
        if status_code != 200:
            raise RunProcessException("Getprint failure (code: %s)", status_code)

        media_type = request.outputs["output"].format.media_type
        reference = context.file_reference(output_file)

        return {
            "output": Link(
                href=reference,
                mime_type=media_type,
                title="GetPrint document",
                length=output_file.stat().st_size,
            ).model_dump(mode="json", by_alias=True, exclude_none=True),
        }
