import datetime

from typing import (
    Callable,
    Optional,
    cast,
)

from pydantic import JsonValue

from qgis.core import (
    Qgis,
    QgsProcessingContext,
    QgsProcessingParameterDateTime,
    QgsProcessingParameters,
    QgsProject,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime

from ...schemas import InputValueError
from .base import (
    InputParameter,
    ProcessingContext,
)

#
# QgsProcessingParameterDateTime
#

DateTimeParameterDataType = Qgis.ProcessingDateTimeParameterDataType


class ParameterDateTime(InputParameter):
    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterDateTime,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> type:
        _type: type

        def to_py(qdt):
            return qdt.toPyDateTime() if qdt.isValid() else None

        default = field.pop("default", None)

        maximum = to_py(param.maximum())
        minimum = to_py(param.minimum())

        # Convert QGIS default to python
        default_to_py: Callable[..., datetime.date | datetime.time]

        match param.dataType():
            case DateTimeParameterDataType.Date:
                _type = datetime.date
                minimum = minimum and minimum.date()
                maximum = maximum and maximum.date()
                convert = QgsProcessingParameters.parameterAsDate
                default_to_py = QDate.toPyDate
            case DateTimeParameterDataType.Time:
                minimum = minimum and minimum.time()
                maximum = maximum and maximum.time()
                _type = datetime.time
                convert = QgsProcessingParameters.parameterAsTime
                default_to_py = QTime.toPyTime
            case _:  # DateTime
                _type = datetime.datetime
                convert = QgsProcessingParameters.parameterAsDateTime
                default_to_py = QDateTime.toPyDateTime

        if default is not None:
            # Default may be a QDate, QTime, QDateTime or an ISO string
            # not matching the parameter data type: let QGIS convert it
            # as it does when running the algorithm
            qdefault = convert(param, {}, QgsProcessingContext())
            if not qdefault.isValid():
                raise InputValueError(
                    f"Invalid default value for parameter {param.name()}: {default}",
                )
            default = default_to_py(qdefault)  # type: ignore[arg-type]

        if maximum:
            field.update(le=maximum)
        if minimum:
            field.update(ge=minimum)

        if not validation_only:
            schema_extra = {}
            if maximum:
                schema_extra["formatMaximum"] = maximum.isoformat()
            if minimum:
                schema_extra["formatMinimum"] = minimum.isoformat()
            field.update(json_schema_extra=schema_extra)

            if default is not None:
                field.update(default=default)

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QDate | QTime | QDateTime:
        _value = self.validate(inp)

        match cast("QgsProcessingParameterDateTime", self._param).dataType():
            case DateTimeParameterDataType.Date:
                _value = QDate(_value)
            case DateTimeParameterDataType.Time:
                _value = QTime(_value)
            case _:  # DateTime
                _value = QDateTime(_value)

        return _value
