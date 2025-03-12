
import datetime

from typing import Optional

from pydantic import JsonValue

from qgis.core import (
    Qgis,
    QgsProcessingParameterDateTime,
    QgsProject,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime

from .base import (
    InputParameter,
    ProcessingContext,
)

#
# QgsProcessingParameterDateTime
#

if Qgis.QGIS_VERSION_INT >= 33600:
    DateTimeParameterDataType = Qgis.ProcessingDateTimeParameterDataType
else:
    DateTimeParameterDataType = QgsProcessingParameterDateTime


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

        default = field.pop('default', None)

        maximum = to_py(param.maximum())
        minimum = to_py(param.minimum())

        match param.dataType():
            case DateTimeParameterDataType.Date:
                _type = datetime.date
                minimum = minimum and minimum.date()
                maximum = maximum and maximum.date()
                default = default and default.toPyDate()
            case DateTimeParameterDataType.Time:
                minimum = minimum and minimum.time()
                maximum = maximum and maximum.time()
                default = default and default.toPyTime()
                _type = datetime.time
            case _:  # DateTime
                _type = datetime.datetime
                default = default and default.toPyDateTime()

        if maximum:
            field.update(le=maximum)
        if minimum:
            field.update(ge=minimum)

        if not validation_only:
            schema_extra = {}
            if maximum:
                schema_extra['formatMaximum'] = maximum.isoformat()
            if minimum:
                schema_extra['formatMinimum'] = minimum.isoformat()
            field.update(json_schema_extra=schema_extra)

            if default:
                field.update(default=default)

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QDate | QTime | QDateTime:

        _value = self.validate(inp)

        match self._param.dataType():
            case DateTimeParameterDataType.Date:
                _value = QDate(_value)
            case DateTimeParameterDataType.Time:
                _value = QTime(_value)
            case _:  # DateTime
                _value = QDateTime(_value)

        return _value
