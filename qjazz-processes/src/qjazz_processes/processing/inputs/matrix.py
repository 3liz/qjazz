from typing import (
    Annotated,
    Any,
    Optional,
    Sequence,
    TypeAlias,
)

from pydantic import Field, JsonValue

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingParameterMatrix,
    QgsProcessingParameters,
    QgsProject,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_postcondition
from qjazz_processes.schemas import (
    Metadata,
    MetadataValue,
    OneOf,
)

from .base import (
    InputParameter,
    ProcessingContext,
)

#
# QgsProcessingParameterMatrix
#


def get_default_value(param, default, project, rows, cols):
    #
    # Validate matrix default value
    #
    if not default:
        return None

    context = QgsProcessingContext()
    if project:
        context.setProject(project)
        context.setExpressionContext(project.createExpressionContext())

    _value = QgsProcessingParameters.parameterAsMatrix(param, default, context)
    if not isinstance(_value, Sequence):
        logger.warning("Invalid matrix default value for: %s", _value)
    elif rows and not cols:
        cols = len(_value) // rows

    if cols:
        try:
            default = [_value[i : i + cols] for i in range(0, len(_value), cols)]
            if rows:
                assert_postcondition(len(default) == rows, "Invalid number of rows")
        except Exception as e:
            logger.error("%s\nInvalid matrix default value %s", e, _value)
    else:
        default = _value

    return default


class ParameterMatrix(InputParameter):
    _SchemaFormat = "x-qgis-matrix"

    @classmethod
    def metadata(cls, param: QgsProcessingParameterMatrix) -> list[Metadata]:
        md = super(ParameterMatrix, cls).metadata(param)
        fixed = param.hasFixedNumberRows()
        md.append(MetadataValue(role="hasFixedNumberRows", value=fixed))
        if fixed:
            md.append(MetadataValue(role="numberRows", value=param.numberRows()))
        return md

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterMatrix,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        headers = param.headers()
        cols = len(headers) if headers else None

        Row: Any = Sequence[OneOf[float | str]]
        if cols:
            Row = Annotated[Row, Field(max_length=cols, min_length=cols)]

        _type: Any = Sequence[Row]

        rows: int | None
        if param.hasFixedNumberRows():
            rows = param.numberRows()
            _type = Annotated[_type, Field(max_length=rows, min_length=rows)]
        else:
            rows = None

        if not validation_only:
            default = get_default_value(
                param,
                field.pop("default", None),
                project,
                rows,
                cols,
            )
            if default:
                field.update(default=default)
            if headers:
                schema_extra = field.get("json_schema_extra", {})
                schema_extra["x-matrix-headers"] = headers
                field.update(json_schema_extra=schema_extra)

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> list:
        _value = self.validate(inp)
        # Flatten the returned data as required
        # for Matrix parameter value
        return [x for row in _value for x in row]
