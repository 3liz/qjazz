from collections.abc import Sequence
from typing import (
    Annotated,
    Iterator,
    Literal,
    Optional,
    cast,
)
from urllib.parse import urlencode

from pydantic import alias_generators
from pydantic.aliases import PydanticUndefined

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.server import (
    QgsServer,
    QgsServerProjectUtils,
)

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

from .formats import WfsOutputFormat
from .models import model_description
from .request import WfsOutputParameters, download_xsd, getfeature_request

# Getprint specifications
# See https://docs.qgis.org/3.34/en/docs/server_manual/services/wms.html


def get_wfs_layers(project: QgsProject) -> Sequence[str]:
    allowed_layers = set(QgsServerProjectUtils.wfsLayerIds(project))
    return tuple(layer.name() for layer in project.mapLayers().values() if layer.id() in allowed_layers)


#
# wfsOutput Process
#


class WfsOutputProcess:
    @classmethod
    def inputs(
        cls,
        project: Optional[QgsProject] = None,
    ) -> Iterator[tuple[str, InputDescription]]:
        """Convert fields to InputDescription"""
        for name, field in WfsOutputParameters.model_fields.items():
            type_: object
            match name:
                case "layer" if project:
                    type_ = Literal[get_wfs_layers(project)]  # type: ignore [misc]
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

    output_formats: Sequence[Format] = tuple(of.value.as_format() for of in WfsOutputFormat)

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

    process_id = "wfsoutput"

    _description_summary: ProcessDescription | None = None
    _version_info = (1, 0)

    @classmethod
    def _description(cls) -> ProcessDescription:
        if not cls._description_summary:
            description = ProcessDescription(
                id_=cls.process_id,  # type: ignore [call-arg]
                title="Wfs Output`",
                description="Return features in various formats",
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
    def output_format(cls, request: JobExecute) -> WfsOutputFormat:
        output = request.outputs.get("output")
        if not output:
            raise InputValueError("Missing output format definition")

        if output.format not in cls.output_formats:
            raise InputValueError(f"Invalid format definition: {output.format.media_type}")

        output_format = cast(WfsOutputFormat, WfsOutputFormat.find_format(output.format))
        assert_precondition(output_format is not None)
        return output_format

    @classmethod
    @classmethod
    def execute(
        cls,
        request: JobExecute,
        feedback: QgsProcessingFeedback,
        context: ProcessingContext,
        server: QgsServer,
    ) -> JobResults:
        """Execute GetPrint request"""

        output_format = cls.output_format(request)
        params = WfsOutputParameters.model_validate(request.inputs)

        basename = params.name or f"{params.layer}-{context.job_id}"

        _query = urlencode(tuple(params.query(output_format)))

        project = context.project()
        assert_precondition(project is not None)

        features_output = getfeature_request(
            basename,
            feedback,
            context,
            server,
            project,
            _query,
            output_format,
        )

        if not output_format.value.is_native():
            # Get the xsd
            # Note that if xsd file available then GDAL will not  create
            # a '.gfs' file locally when reading the gml
            if download_xsd(basename, params.layer, feedback, context, server, project):
                options = "|option:FORCE_SRS_DETECTION=YES"
            else:
                options = ""

            # Create layer
            output_layer = QgsVectorLayer(f"{features_output}{options}", basename, "ogr")
            if not output_layer.isValid():
                raise RunProcessException("Invalid GML layer")

            # Save file as requested format
            wr_opts = QgsVectorFileWriter.SaveVectorOptions()
            wr_opts.driverName = output_format.value.ogr_provider
            wr_opts.fileEncoding = "utf-8"

            if output_format.value.crs:
                wr_opts.ct = QgsCoordinateTransform(
                    output_layer.crs(),
                    QgsCoordinateReferenceSystem(output_format.value.crs),
                    project,
                )

            if output_format.value.ogr_options:
                wr_opts.datasourceOptions = output_format.value.ogr_options

            output_file = features_output.with_suffix(output_format.value.suffix)

            result, error_message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
                output_layer,
                str(output_file),
                project.transformContext(),
                wr_opts,
            )

            if result != QgsVectorFileWriter.NoError:
                raise RunProcessException(error_message)

            if output_format == WfsOutputFormat.SHP:
                # For shapefile add the codepage file
                output_file.with_suffix(".cpg").write_text(f"{wr_opts.fileEncoding}\n")

            media_type = output_format.value.media_type

            # Compress if required
            if output_format.value.archive:
                from .archive import archive_files

                output_file = archive_files(output_file, output_format.value, feedback, context)
        else:
            # Nothing else to do
            media_type = request.outputs["output"].format.media_type
            output_file = features_output

        reference = context.file_reference(output_file)

        return {
            "output": Link(
                href=reference,
                mime_type=media_type,
                title=f"WfsOutput {params.name} document",
                length=output_file.stat().st_size,
            ).model_dump(mode="json", by_alias=True, exclude_none=True),
        }
