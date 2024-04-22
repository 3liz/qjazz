
from collections import Counter

from qgis.core import (
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
)

from py_qgis_processes.schemas.qgis.inputs import InputParameter


def test_parameter_description():

    param = QgsProcessingParameterString(
        "String",
        description="String description",
    )
    param.setHelp("String help")

    inp = InputParameter(param)

    descr = inp.description()
    assert descr.title == "String description"
    assert descr.description == "String help"


def test_parameter_string():

    param = QgsProcessingParameterString("String")

    inp = InputParameter(param)

    schema = inp.json_schema()

    print("\ntest_parameter_string:", schema)

    assert schema['type'] == 'string'


def test_parameter_enum():

    param = QgsProcessingParameterEnum(
        "Enum",
        options=["foo", "bar", "baz"],
        allowMultiple=False,
        defaultValue=1,
    )

    inp = InputParameter(param)

    schema = inp.json_schema()

    print("\ntest_parameter_enum:", schema)

    assert schema['type'] == 'string'
    assert schema['default'] == 'bar'
    
    value = inp.value("bar")
    assert value == 1

    assert param.checkValueIsAcceptable(value)


def test_parameter_enum_multiple():

    param = QgsProcessingParameterEnum(
        "Enum",
        options=["foo", "bar", "baz"],
        allowMultiple=True,
    )

    inp = InputParameter(param)

    schema = inp.json_schema()

    print("\ntest_parameter_enum_multiple:", schema)

    assert schema['type'] == 'array'
    
    value = inp.value(["foo", "bar"])
    assert Counter(value) == Counter([0, 1])

    assert param.checkValueIsAcceptable(value)
    assert not param.checkValueIsAcceptable(["foo", "bar"])

    param.setUsesStaticStrings(True)
    value = inp.value(["foo", "bar"])

    print("test_parameter_enum_multiple:", value)

    assert Counter(value) == Counter(["foo", "bar"])
    assert param.checkValueIsAcceptable(value)


def test_parameter_number():
    # TODO
    pass



