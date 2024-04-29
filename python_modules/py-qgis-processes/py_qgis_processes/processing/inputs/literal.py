
import datetime
import sys

from pydantic import Field, JsonValue
from pydantic_extra_types.color import Color
from qgis.core import (
    Qgis,
    QgsProcessingParameterBand,
    QgsProcessingParameterColor,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterDistance,
    QgsProcessingParameterDuration,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRange,
    QgsProcessingParameterScale,
    QgsProject,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime
from qgis.PyQt.QtGui import QColor
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Type,
)

from py_qgis_processes_schemas import (
    InputValueError,
    OgcDataType,
    ogc,
)

from .base import InputParameter

#
# QgsProcessingParameterBoolean
#


class ParameterBool(InputParameter):
    _ParameterType = bool


#
# QgsProcessingParameterString
#

class ParameterString(InputParameter):
    _ParameterType = str


#
# QgsProcessingParameterEnum
#

class ParameterEnum(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterEnum,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        opts = tuple(param.options())

        _type = Literal[opts]  # type: ignore [valid-type]

        multiple = param.allowMultiple()

        if multiple:
            _type = Set[_type]  # type: ignore [misc]

        if not validation_only:
            default = field.get('default')

            if default is not None:
                match default:
                    case str() if multiple:
                        default = set(default.split(','))
                    case [str(), *_]:
                        default = set(default) if multiple else default[0]
                    case [int(), *_]:
                        if multiple:
                            default = set(opts[k] for k in default)
                        else:
                            default = opts[default[0]]
                    case int():
                        default = opts[default]
                    case str():
                        pass
                    case _:
                        raise InputValueError(f"Invalid default Enum value: {default}")

                field.update(default=default)
                field.update(json_schema_extra={'format': "x-qgis-parameter-enum"})

        return _type

    def value(self, inp: JsonValue, project: Optional[QgsProject] = None) -> int | Sequence[int]:

        _value = self.validate(inp)

        opts = self._param.options()

        if not self._param.usesStaticStrings():
            if self._param.allowMultiple():
                _value = [opts.index(v) for v in _value]
            else:
                _value = opts.index(_value)
        elif self._param.allowMultiple():
            _value = list(_value)

        return _value

#
# QgsProcessingParameterNumber
#


def set_number_minmax(param: QgsProcessingParameterNumber, field: Dict):

    minimum = param.minimum()
    maximum = param.maximum()

    # XXX Take care: javascript does not supports 64 bits integer
    # natively
    float_max = sys.float_info.max
    if minimum > -float_max:
        field.update(ge=minimum)
    if maximum < float_max:
        field.update(le=maximum)


class ParameterNumber(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterNumber,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Type[float | int]

        set_number_minmax(param, field)

        match param.dataType():
            case QgsProcessingParameterNumber.Double:
                _type = float
            case QgsProcessingParameterNumber.Integer:
                _type = int
            case invalid:
                raise InputValueError(f"Invalid type for number: {invalid}")

        return _type

#
# QgsProcessingParameterDistance
#


class ParameterDistance(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterDistance,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type = float

        set_number_minmax(param, field)

        unit = param.defaultUnit()
        if unit == Qgis.DistanceUnit.Unknown:
            ref = None
        else:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)

        if not validation_only:
            schema_extra = {'x-ogc-definition': OgcDataType['length']}
            if ref:
                schema_extra['x-ogc-uom'] = ref
                schema_extra['x-ogc-uom-name'] = uom

            field.update(json_schema_extra=schema_extra)

        set_number_minmax(param, field)
        return _type


#
# QgsProcessingParameterScale
#

class ParameterScale(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterScale,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type = float

        set_number_minmax(param, field)

        if not validation_only:
            field.update(json_schema_extra={'x-ogc-definition': OgcDataType['scale']})

        return _type


class ParameterDuration(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterDuration,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type = float

        set_number_minmax(param, field)

        unit = param.defaultUnit()
        if unit == Qgis.TemporalUnit.Unknown:
            ref = None
        else:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)

        if not validation_only:
            schema_extra = {'x-ogc-definition': OgcDataType['time']}
            if ref:
                schema_extra['x-ogc-uom'] = ref
                schema_extra['x-ogc-uom-name'] = uom

            field.update(json_schema_extra=schema_extra)

        return _type


#
# QgsProcessingParameterRange
#
if Qgis.QGIS_VERSION_INT >= 33600:
    NumberParameterType = Qgis.ProcessingNumberParameterType
else:
    NumberParameterType = QgsProcessingParameterNumber


class ParameterRange(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterRange,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        default = field.get('default')

        _type: Type

        match param.dataType():
            case NumberParameterType.Integer:
                _type = int
            case NumberParameterType.Double:
                _type = float

        field.update(min_length=2, max_length=2)

        if not validation_only:
            if default is not None:
                match default:
                    case [float(), float()] | [int(), int()]:
                        pass
                    case str():
                        left, right = default.split(':')
                        field.update(default=[_type(left), _type(right)])
                    case _:
                        InputValueError(f"Invalid default value for parameter Range: {default}")

            field.update(json_schema_extra={'format': "x-qgis-parameter-range"})

        _type = Sequence[_type]  # type: ignore [valid-type]
        return _type


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
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Type

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

    def value(self, inp: JsonValue, project: Optional[QgsProject] = None) -> QDate | QTime | QDateTime:

        _value = self.validate(inp)

        match self._param.dataType():
            case DateTimeParameterDataType.Date:
                _value = QDate(_value)
            case DateTimeParameterDataType.Time:
                _value = QTime(_value)
            case _:  # DateTime
                _value = QDateTime(_value)

        return _value


#
# QgsProcessingParameterBand
#

class ParameterBand(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterBand,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = Annotated[int, Field(ge=0)]  #

        if param.allowMultiple():
            _type = Annotated[List[_type], Field(min_length=1)]  # type: ignore [misc]

        if not validation_only:
            schema_extra = {
                'format': "x-qgis-parameter-band",
            }

            parent_layer_param = param.parentLayerParameterName()
            if parent_layer_param:
                schema_extra['x-qgis-parentLayerParameterName'] = parent_layer_param

            field.update(json_schema_extra=schema_extra)

        return _type


#
# QgsProcessingParameterColor
#

class ParameterColor(InputParameter):
    # CSS3 color

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterColor,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        if not validation_only:
            default = field.pop('default', None)
            match default:
                case str():
                    from qgis.core import QgsSymbolLayerUtils
                    default = QgsSymbolLayerUtils.parseColor(default)
                case QColor():
                    pass
                case _:
                    raise InputValueError(f"Invalid default value for color: {default}")

            # XXX: QColor has not not the same color hex representation as
            # CSS3 spec (i.e QColor: '#aarrggbb', CSS3: '#rrggbbaa')
            # Use non ambiguous representation
            if default and default.isValid():
                c = default
                field.update(default=Color(f"rgb({c.red()},{c.green()},{c.blue()},{c.alphaF()})"))

        return Color

    def value(self, inp: JsonValue, project: Optional[QgsProject] = None) -> QColor:

        _value = self.validate(inp)

        rgb = _value.as_rgb_tuple()

        qcolor = QColor(rgb[0], rgb[1], rgb[2])
        if self._param.opacityEnabled() and len(rgb) > 3:
            qcolor.setAlphaF(rgb[3])

        return qcolor


#
# QgsProcessingParameterField
#

if Qgis.QGIS_VERSION_INT >= 33600:
    FieldParameterDataType = Qgis.ProcessingFieldParameterDataType
    def field_datatype_name(value: Qgis.ProcessingFieldParameterDataType) -> str:
        return value.name
else:
    FieldParameterDataType = QgsProcessingParameterField
    def field_datatype_name(value: int) -> str:   # type: ignore [misc]
        match value:
            case QgsProcessingParameterField.Any:
                field_datatype = 'Any'
            case QgsProcessingParameterField.Numeric:
                field_datatype = 'Numeric'
            case QgsProcessingParameterField.String:
                field_datatype = 'String'
            case QgsProcessingParameterField.DateTime:
                field_datatype = 'DateTime'
            case QgsProcessingParameterField.Binary:
                field_datatype = 'Binary'
            case QgsProcessingParameterField.Boolean:
                field_datatype = 'Boolean'
            case _:
                raise ValueError(f"Unexpected field_datatype: {value}")
        return field_datatype


class ParameterField(InputParameter):
    # CSS3 color

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterField,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = str  #

        if param.allowMultiple():
            _type = Annotated[List[_type], Field(min_length=1)]  # type: ignore [misc]

        if not validation_only:
            schema_extra = {
                'format': "x-qgis-parameter-field",
                'x-qgis-field-dataType': field_datatype_name(param.dataType()),
            }

            parent_layer_param = param.parentLayerParameterName()
            if parent_layer_param:
                schema_extra['x-qgis-parentLayerParameterName'] = parent_layer_param

            field.update(json_schema_extra=schema_extra)

        return _type
