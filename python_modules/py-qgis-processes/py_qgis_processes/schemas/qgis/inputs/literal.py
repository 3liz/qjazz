import sys

from pydantic import JsonValue
from qgis.core import (
    Qgis,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRange,
    QgsProcessingParameterScale,
    QgsProject,
    QgsUnitTypes,
)
from typing_extensions import (
    Dict,
    Literal,
    Optional,
    Self,
    Sequence,
    Set,
    Type,
)

from ...ogc import OgcDataType, UOMRef
from .base import InputParameter

#
# QgsProcessingParameterBoolean
#


class ParameterBool(InputParameter):
    _BasicType = bool


#
# QgsProcessingParameterString
#

class ParameterString(InputParameter):
    _BasicType = str


#
# QgsProcessingParameterEnum
#

class ParameterEnum(InputParameter):

    @classmethod
    def create_model(
        cls: Type[Self],
        param: QgsProcessingParameterEnum,
        field: Dict,
        project: Optional[QgsProject] = None,
    ) -> Type:

        opts = tuple(param.options())

        _type = Literal[opts]  # type: ignore [valid-type]

        multiple = param.allowMultiple()

        if multiple:
            _type = Set[_type]  # type: ignore [misc]

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
                    raise ValueError(f"Invalid default Enum value: {default}") 

            field.update(default=default)    

        field.update(json_schema_extra={'format': "x-qgis-parameter-enum"})
        return _type

    def value(self, inp: JsonValue) -> int | Sequence[int]:

        _value = self._model.validate_python(inp)

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
    if minimum > sys.float_info.min:
        field.update(ge=minimum)
    if maximum < sys.float_info.max:
        field.update(le=maximum)


class ParameterNumber(InputParameter):

    @classmethod
    def create_model(
        cls: Type[Self],
        param: QgsProcessingParameterNumber,
        field: Dict,
        project: Optional[QgsProject] = None,
    ) -> Type:

        _type: Type[float | int]

        set_number_minmax(param, field)

        match param.dataType():
            case QgsProcessingParameterNumber.Double:
                _type = float
                field.update(json_schema_extra={'contentSchema': OgcDataType['double']})
            case QgsProcessingParameterNumber.Integer:
                _type = int
                field.update(json_schema_extra={'contentSchema': OgcDataType['signedInt']})
            case invalid:
                raise ValueError(f"Invalid type for number: {invalid}")

        return _type

#
# QgsProcessingParameterDistance
#


class ParameterDistance(InputParameter):

    @classmethod
    def create_model(
        cls: Type[Self],
        param: QgsProcessingParameterDistance,
        field: Dict,
        project: Optional[QgsProject] = None,
    ) -> Type:

        _type = float

        set_number_minmax(param, field)

        unit = param.defaultUnit()
        if unit == Qgis.DistanceUnit.Unknown:
            ref = None
        else:
            uom = QgsUnitTypes.toString(unit)
            ref = UOMRef.from_name(uom)

        schema_extra = dict(contentSchema=OgcDataType['length'])
        if ref:
            schema_extra['format'] = str(ref)
            schema_extra['x-uom-name'] = uom

        set_number_minmax(param, field)

        field.update(json_schema_extra=schema_extra)
        return _type


#
# QgsProcessingParameterScale
#

class ParameterScale(InputParameter):

    @classmethod
    def create_model(
        cls: Type[Self],
        param: QgsProcessingParameterScale,
        field: Dict,
        project: Optional[QgsProject] = None,
    ) -> Type:

        _type = float

        set_number_minmax(param, field)

        field.update(json_schema_extra={'contentSchema': OgcDataType['scale']})
        return _type


#
# QgsProcessingParameterRange
#

class ParameterRange(InputParameter):

    @classmethod
    def create_model(
        cls: Type[Self],
        param: QgsProcessingParameterRange,
        field: Dict,
        project: Optional[QgsProject] = None,
    ) -> Type:

        default = field.get('default')

        _type: Type

        match param.dataType():
            case Qgis.ProcessingNumberParameterType.Integer:
                _type = int
            case Qgis.ProcessingNumberParameterType.Double:
                _type = float

        if default is not None:
            match default:
                case [float(), float()] | [int(), int()]:
                    pass
                case str():
                    left, right = default.split(':')
                    field.update(default=[_type(left), _type(right)])
                case _:
                    ValueError(f"Invalid default value for parameter Range: {default}")

        _type = Sequence[_type]  # type: ignore [valid-type]

        field.update(
            min_length=2,
            max_length=2,
            json_schema_extra={'format': "x-qgis-parameter-range"},
        )

        return _type
