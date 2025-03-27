from collections.abc import Sequence
from contextlib import contextmanager
from typing import (
    Annotated,
    Any,
    Generator,
    Iterable,
    Iterator,
    Literal,
    Optional,
    cast,
)

from qgis.core import QgsProject

from qjazz_processes.schemas import (
    Field,
    JsonModel,
    Option,
)
from qjazz_processes.schemas.bbox import Extent2D

# Getprint specifications
# See https://docs.qgis.org/3.34/en/docs/server_manual/services/wms.html


def _to_bool_param(b: bool) -> str:
    return "TRUE" if b else "FALSE"


def _comma_separated_list(seq: Sequence[str | int | float], sep: str = ",") -> str:
    return sep.join(str(v) for v in seq)


class PdfFormatOptions(JsonModel):
    rasterize_whole_image: Option[bool] = Field(
        title="Export as image",
        description="Whether the whole pdf should be exported as an image,",
    )
    force_vector_output: Option[bool] = Field(
        title="Export as vector",
        description="Whether pdf should be exported as vector.",
    )
    append_georeference: Option[bool] = Field(
        title="Add georeference",
        description="Whether georeference info shall be added to the pdf.",
    )
    export_metadata: Option[bool] = Field(
        title="Export metadata",
        description="Whether metadata shall be added to the pdf.",
    )
    text_render_format: Option[Literal["AlwaysOutline", "AlwaysText"]] = Field(
        title="Text render format",
        description="Sets the text render format for pdf export",
    )
    simplify_geometry: Option[bool] = Field(
        title="Simplify geometries",
    )
    write_geo_pdf: Option[bool] = Field(
        title="Export as GeoPDF",
    )
    use_iso_32000_extension_format_georeferencing: Option[bool] = Field(
        title="Use Iso32000 georeferencing",
    )
    use_ogc_best_practice_format_georeferencing: Option[bool] = Field(
        title="Use ogc best practice georeferencing",
    )
    export_themes: Option[str] = Field(
        title="Exported themes",
        description="A comma separated list of map themes to use for a GeoPDF export",
    )
    predefined_map_scales: Option[str] = Field(
        title="Map scales",
        description="A comma separated list of map scales to render the map.",
    )
    lossless_image_compression: Option[bool] = Field(
        title="Use lossless compression",
        description="Whether images embedded in pdf must be compressed using a lossless algorithm.",
    )
    disable_tiled_raster_rendering: Option[bool] = Field(
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
    extent: Option[Extent2D] = Field(
        title="Extent",
        description="""
        This parameter specifies the extent for a layout map item
        as [xmin,ymin,xmax,ymax].
        """,
    )
    rotation: Option[float] = Field(
        title="Rotation",
        description="This parameter specifies the map rotation in degrees.",
    )
    grid_interval_x: Option[int] = Field(
        title="Grid interval X",
        description="This parameter specifies the grid line density in the X direction.",
    )
    grid_interval_y: Option[int] = Field(
        title="Grid interval Y",
        description="This parameter specifies the grid line density in the Y direction.",
    )
    scale: Option[float] = Field(
        title="Scale",
        description="""
        This parameter specifies the map scale for a layout map item.
        This is useful to ensure scale based visibility of layers and labels
        even if client and server may have different algorithms to calculate
        the scale denominator.
        """,
    )
    layers: Option[Sequence[str]] = Field(title="Layers")
    styles: Option[Sequence[str]] = Field(title="Styles")

    def to_query_params(self, name: str) -> Iterator[tuple[str, str]]:
        for field, val in self.model_dump().items():
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
DpiValue = Annotated[int, Field(ge=72, le=2400)]


#
# GetPrint Parameters
#

class GetPrintParameters(JsonModel):
    template: str = Field(
        title="Layout template",
        description="Layout template to use",
    )
    crs: str = Field(
        title="Coordinate reference system",
        description="""
            This parameter allows to indicate the map output
            Coordinate Reference System.
        """,
    )
    dpi: Option[DpiValue] = Field(
        title="Dpi",
        description="Dpi value for the final document",
    )
    format_options: Option[PdfFormatOptions] = Field(
        title="Pdf format options",
        description="Options for pdf output format only",
    )
    atlas_pk: Option[str] = Field(
        title="Atlas features",
        description="""
        This parameter allows activation of Atlas rendering by indicating
        which features we want to print.
        In order to retrieve an atlas with all features, the * symbol
        may be used (according to the maximum number of features allowed
        in the project configuration).
        """,
    )
    styles: Option[Sequence[str]] = Field(
        title="Layer's style",
        description="""
        This parameter can be used to specify a layer's style
        for the rendering step.
        """,
    )
    transparent: Option[bool] = Field(
        title="Transparent background",
        description="This parameter can be used to specify the background transparency.",
    )
    opacities: Option[Sequence[OpacityValue]] = Field(
        title="Opacity for layer or group",
        description="""
        List of opacity values.
        Opacity can be set on layer or group level.
        Allowed values range from 0 (fully transparent) to 255 (fully opaque).
        """,
    )
    selection: Option[dict[str, Sequence[FeatureId]]] = Field(
        title="Highlight features",
        description="""
        This parameter can highlight features from one or more layers.
        Vector features can be selected by passing comma separated lists
        with feature ids.
        """,
    )
    layers: Option[Sequence[str]] = Field(
        title="Layers to display",
        description="This parameter allows to specify the layers to display on the map.",
    )
    map_options: dict[str, MapOptions] = Field(
        {},
        title="Layout map item options",
        description="Allow specify layout item options",
    )
    custom_variables: Option[dict[str, str]] = Field(
        title="Variables",
        description="Print context custom variables.",
    )

    @contextmanager
    def set_custom_variables(self, project: QgsProject) -> Generator[dict[str, Any], None, None]:
        variables: Optional[dict] = None
        if self.custom_variables:
            # Override with custom variables from parameter
            variables = cast(dict, project.customVariables())
            custom_variables = variables.copy()
            custom_variables.update(self.custom_variables)
            project.setCustomVariables(custom_variables)
        else:
            custom_variables = {}
        try:
            yield custom_variables
        finally:
            if variables:
                # Restore custom variables
                project.setCustomVariables(variables)

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
        if self.dpi:
            # XXX DPI is not documented in QGIS GetPrint
            yield "DPI", str(self.dpi)
        if self.map_options:
            for name, opts in self.map_options.items():
                yield from opts.to_query_params(name)
