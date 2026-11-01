import math
import sys

from typing import (
    Any,
    Literal,
    Optional,
    Sequence,
    TypeAlias,
)

from pydantic import JsonValue
from pydantic_extra_types.color import Color

from qgis.core import (
    Qgis,
    QgsProcessingParameterArea,
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

from qjazz_processes.schemas import (
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
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        opts = tuple(param.options())

        _type = Literal[opts]  # type: ignore [valid-type]

        multiple = param.allowMultiple()

        if multiple:
            # Allow multiple selection
            _type = set[_type]  # type: ignore [misc]

        if not validation_only:
            default = field.get("default")

            if default is not None:
                field.update(default=cls.enum_default(param, default, opts, multiple))

        return _type

    @classmethod
    def enum_default(
        cls,
        param: QgsProcessingParameterEnum,
        default: Any,
        opts: Sequence[str],
        multiple: bool,
    ) -> str | set[str]:
        """Convert a default value to option(s)

        Without static strings, QGIS enum values are option indexes:
        a string default is a comma separated list of indexes.
        With static strings, values are the options themselves.
        """

        def option(index: int) -> str:
            if not 0 <= index < len(opts):
                raise IndexError(index)
            return opts[index]

        try:
            match default:
                case str() if not param.usesStaticStrings():
                    options = [option(int(i)) for i in default.split(",")]
                    return set(options) if multiple else options[0]
                case str() if multiple:
                    return set(default.split(","))
                case str():
                    return default
                case [str(), *_]:
                    return set(default) if multiple else default[0]
                case [int(), *_]:
                    return {option(k) for k in default} if multiple else option(default[0])
                case int():
                    return option(default)
        except (ValueError, IndexError):
            pass

        raise InputValueError(f"Invalid default Enum value: {default}")

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


def set_number_minmax(param: QgsProcessingParameterNumber, field: dict, integer: bool = False):
    minimum = param.minimum()
    maximum = param.maximum()

    # XXX Take care: javascript does not supports 64 bits integer
    # natively
    float_max = sys.float_info.max
    if minimum > -float_max:
        # Integer parameters may have non integer bounds
        # (i.e 'native:createrandomnegativebinomialrasterlayer'):
        # use the integer bounds within the range
        field.update(ge=math.ceil(minimum) if integer else minimum)
    if maximum < float_max:
        field.update(le=math.floor(maximum) if integer else maximum)


class ParameterNumber(InputParameter):
    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterNumber,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        _type: type[float | int]

        match param.dataType():
            case Qgis.ProcessingNumberParameterType.Double:
                _type = float
            case Qgis.ProcessingNumberParameterType.Integer:
                _type = int
            case invalid:
                raise InputValueError(f"Invalid type for number: {invalid}")

        set_number_minmax(param, field, integer=_type is int)

        return _type


#
# QgsProcessingParameterArea
#


class ParameterArea(ParameterNumber):
    @classmethod
    def metadata(cls, param: QgsProcessingParameterArea) -> list[Metadata]:
        md = super(ParameterArea, cls).metadata(param)
        # Note: there is no OGC data type for area
        md.append(MetadataLink(role="ogcType", href=OgcDataType["measure"], title="measure"))

        unit = param.defaultUnit()
        if unit != Qgis.AreaUnit.Unknown:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)
            if ref:
                md.append(
                    MetadataLink(
                        role="uom",
                        href=ref,
                        title=uom,
                    ),
                )
            else:
                # No standard reference found
                md.append(
                    MetadataValue(
                        role="uom",
                        title=uom,
                        value=QgsUnitTypes.toAbbreviatedString(unit),
                    ),
                )

        parent_param = param.parentParameterName()
        if parent_param:
            md.append(
                MetadataValue(
                    role="parentParameterName",
                    value=parent_param,
                ),
            )

        return md


#
# QgsProcessingParameterDistance
#


class ParameterDistance(ParameterNumber):
    @classmethod
    def metadata(cls, param: QgsProcessingParameterDistance) -> list[Metadata]:
        md = super(ParameterDistance, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType["length"], title="length"))

        unit = param.defaultUnit()
        if unit != Qgis.DistanceUnit.Unknown:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)
            if ref:
                md.append(
                    MetadataLink(
                        role="uom",
                        href=ref,
                        title=uom,
                    ),
                )
            else:
                # No standard reference found
                md.append(
                    MetadataValue(
                        role="uom",
                        title=uom,
                        value=QgsUnitTypes.toAbbreviatedString(unit),
                    ),
                )

        parent_param = param.parentParameterName()
        if parent_param:
            md.append(
                MetadataValue(
                    role="parentParameterName",
                    value=parent_param,
                ),
            )

        return md


#
# QgsProcessingParameterScale
#


class ParameterScale(ParameterNumber):
    @classmethod
    def metadata(cls, param: QgsProcessingParameterScale) -> list[Metadata]:
        md = super(ParameterScale, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType["scale"], title="scale"))

        return md


#
# QgsProcessingParameterDuration
#


class ParameterDuration(ParameterNumber):
    @classmethod
    def metadata(cls, param: QgsProcessingParameterDuration) -> list[Metadata]:
        md = super(ParameterDuration, cls).metadata(param)
        md.append(MetadataLink(role="ogcType", href=OgcDataType["time"], title="time"))

        unit = param.defaultUnit()
        if unit != Qgis.TemporalUnit.Unknown:
            uom = QgsUnitTypes.toString(unit)
            ref = ogc.uom_ref(uom)
            if ref:
                md.append(
                    MetadataLink(
                        role="uom",
                        href=ref,
                        title=uom,
                    ),
                )
            else:
                md.append(
                    MetadataValue(
                        role="uom",
                        title=uom,
                        value=QgsUnitTypes.toAbbreviatedString(unit),
                    ),
                )

        return md


#
# QgsProcessingParameterRange
#

NumberParameterType = Qgis.ProcessingNumberParameterType


class ParameterRange(InputParameter):
    _SchemaFormat = "x-range"

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterRange,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        default = field.get("default")

        _type: type

        match param.dataType():
            case NumberParameterType.Integer:
                _type = int
            case _:
                _type = float

        field.update(min_length=2, max_length=2)

        if not validation_only and default is not None:
            field.update(default=cls.range_default(default, _type))

        _type = Sequence[_type]  # type: ignore [valid-type]
        return _type

    @classmethod
    def range_default(cls, default: Any, _type: type) -> list[int] | list[float]:
        """Parse a range default value

        QGIS defines range values either as a 'min,max'
        string or as a list of two numbers
        """
        match default:
            case str():
                values = default.split(",")
            case list():
                values = default
            case _:
                values = []

        try:
            if len(values) != 2:
                raise ValueError()
            numbers = [float(v) for v in values]
            if not all(math.isfinite(n) for n in numbers):
                raise ValueError()
            if _type is int:
                if not all(n.is_integer() for n in numbers):
                    raise ValueError()
                return [int(n) for n in numbers]
            return numbers
        except (TypeError, ValueError):
            raise InputValueError(f"Invalid default value for parameter Range: {default}") from None


#
# QgsProcessingParameterColor
#


class ParameterColor(InputParameter):
    # CSS3 color

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterColor,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        if not validation_only:
            default = field.pop("default", None)
            match default:
                case str():
                    from qgis.core import QgsSymbolLayerUtils

                    default = QgsSymbolLayerUtils.parseColor(default)
                case QColor():
                    pass
                case None:
                    # No default value
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
    def metadata(cls, param: QgsProcessingParameterDatabaseSchema) -> list[Metadata]:
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
    def metadata(cls, param: QgsProcessingParameterDatabaseTable) -> list[Metadata]:
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
#  QgsProcessingParameterAuthConfig
#


class ParameterAuthConfig(ParameterString):
    pass


#
# QgisProcessingParameterLayout
#


class ParameterLayout(InputParameter):
    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterLayout,
        field: dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        _type: Any = str

        if project:
            managers = project.layoutManager()
            if managers is not None:
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
    def metadata(cls, param: QgsProcessingParameterLayoutItem) -> list[Metadata]:
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
