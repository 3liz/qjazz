
import sys

from pydantic import JsonValue
from pydantic_extra_types.color import Color
from typing_extensions import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Type,
    TypeAlias,
)

from qgis.core import (
    Qgis,
    QgsProcessingParameterColor,
    QgsProcessingParameterDatabaseSchema,
    QgsProcessingParameterDatabaseTable,
    QgsProcessingParameterDistance,
    QgsProcessingParameterDuration,
    QgsProcessingParameterEnum,
    QgsProcessingParameterLayout,
    QgsProcessingParameterLayoutItem,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRange,
    QgsProcessingParameterScale,
    QgsProject,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor

from py_qgis_processes_schemas import (
    InputValueError,
    Metadata,
    MetadataLink,
    MetadataValue,
    OgcDataType,
    ogc,
)

from .base import (
    InputParameter,
    ProcessingContext,
)

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
    ) -> TypeAlias:

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

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> int | Sequence[int]:

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
    ) -> TypeAlias:

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

class ParameterDistance(ParameterNumber):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterDistance) -> List[Metadata]:
        md = super(ParameterDistance, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType['length'], title="length"))

        unit = param.defaultUnit()
        if unit != Qgis.DistanceUnit.Unknown:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)
            if ref:
                md.append(
                    MetadataLink(
                        role="uom",
                        href=ogc.uom_ref(uom),
                        title=uom,
                    ),
                )
        return md


#
# QgsProcessingParameterScale
#


class ParameterScale(ParameterNumber):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterScale) -> List[Metadata]:
        md = super(ParameterScale, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType['scale'], title="scale"))

        return md


#
# QgsProcessingParameterDuration
#

class ParameterDuration(ParameterNumber):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterDuration) -> List[Metadata]:
        md = super(ParameterDuration, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType['time'], title="time"))

        unit = param.defaultUnit()
        if unit != Qgis.TemporalUnit.Unknown:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)
            if ref:
                md.append(
                    MetadataLink(
                        role="uom",
                        href=ogc.uom_ref(uom),
                        title=uom,
                    ),
                )
        return md

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
    ) -> TypeAlias:

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

            field.update(json_schema_extra={'format': "x-range"})

        _type = Sequence[_type]  # type: ignore [valid-type]
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
    ) -> TypeAlias:

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

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> QColor:

        _value = self.validate(inp)

        rgb = _value.as_rgb_tuple()

        qcolor = QColor(rgb[0], rgb[1], rgb[2])
        if self._param.opacityEnabled() and len(rgb) > 3:
            qcolor.setAlphaF(rgb[3])

        return qcolor


#
# QgsProcessingParameterDatabaseSchema
#


class ParameterDatabaseSchema(ParameterString):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterDatabaseSchema) -> List[Metadata]:
        md = super(ParameterDatabaseSchema, cls).metadata(param)
        parent_connection_param = param.parentConnectionParameterName()
        if parent_connection_param:
            md.append(
                MetadataValue(
                    role="parentConnectionParameterName",
                    value=parent_connection_param,
                ),
            )

        return md


#
# QgsProcessingParameterDatabaseTable
#


class ParameterDatabaseTable(ParameterString):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterDatabaseTable) -> List[Metadata]:
        md = super(ParameterDatabaseTable, cls).metadata(param)
        md.append(MetadataValue(role="allowNewTableNames", value=param.allowNewTableNames()))

        parent_connection_param = param.parentConnectionParameterName()
        if parent_connection_param:
            md.append(
                MetadataValue(
                    role="parentConnectionParameterName",
                    value=parent_connection_param,
                ),
            )

        return md


#
#  QgsProcessingParameterProviderConnection
#

class ParameterProviderConnection(ParameterString):
    pass


#
# QgisProcessingParameterLayout
#

class ParameterLayout(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterLayout,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:

        _type: Any = str

        if project:
            managers = project.layoutManager()
            values = tuple(layout.name() for layout in managers.printLayouts())
            if values:
                _type = Literal[values]

        return _type

#
# QgisProcessingParameterLayoutItem
#


class ParameterLayoutItem(InputParameter):
    _ParameterType = str

    @classmethod
    def metadata(cls, param: QgsProcessingParameterLayoutItem) -> List[Metadata]:
        md = super(ParameterLayoutItem, cls).metadata(param)
        parent_layout_parameter = param.parentLayoutParameterName()
        if parent_layout_parameter:
            md.append(
                MetadataValue(
                    role="parentLayoutParameterName",
                    value=parent_layout_parameter,
                ),
            )

        return md

#
# QgisProcessingParameterMapTheme
#


class ParameterMapTheme(InputParameter):
    _ParameterType = str
