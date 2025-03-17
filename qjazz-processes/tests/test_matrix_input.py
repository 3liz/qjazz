import pytest

from pydantic import ValidationError

from qgis.core import QgsProcessingParameterMatrix

from qjazz_processes.processing.inputs import (
    InputParameter,
    ParameterMatrix,
)


def meta(seq, s):
    return next(filter(lambda m: m.role == s, seq)).value


def test_parameter_matrix():
    headers = ["A", "B", "C"]
    param = QgsProcessingParameterMatrix("Matrix", headers=headers)

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMatrix)

    schema = inp.json_schema()
    print("\ntest_parameter_matrix::", schema)
    assert schema["format"] == "x-matrix"
    assert schema["x-matrix-headers"] == headers

    md = inp.metadata(param)
    assert meta(md, "typeName") == QgsProcessingParameterMatrix.typeName()
    assert not meta(md, "hasFixedNumberRows")

    value = inp.value([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert value == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

    # Test incomplete row is invalid
    with pytest.raises(ValidationError):
        _ = inp.value([[1.0, 2.0, 3.0], [4.0]])


def test_parameter_matrix_fixed_rows():
    param = QgsProcessingParameterMatrix(
        "Matrix",
        headers=["A", "B", "C"],
        hasFixedNumberRows=True,
        numberRows=3,
    )

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMatrix)

    schema = inp.json_schema()
    print("\ntest_parameter_matrix_fixed_rows::", schema)
    assert schema["format"] == "x-matrix"

    md = inp.metadata(param)
    assert meta(md, "typeName") == QgsProcessingParameterMatrix.typeName()
    assert meta(md, "hasFixedNumberRows")
    assert meta(md, "numberRows") == 3

    value = inp.value([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    assert value == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]

    assert param.checkValueIsAcceptable(value)

    # Test missing row is invalid
    with pytest.raises(ValidationError):
        _ = inp.value([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def test_parameter_matrix_no_headers():
    param = QgsProcessingParameterMatrix(
        "Matrix",
        headers=["A", "B"],
        hasFixedNumberRows=True,
        numberRows=3,
    )

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMatrix)

    schema = inp.json_schema()
    print("\ntest_parameter_matrix_no_headers::", schema)

    value = inp.value([[1.0, 2.0], [4.0, 5.0], [6.0, 7.0]])
    assert value == [1.0, 2.0, 4.0, 5.0, 6.0, 7.0]

    # Test missing row is invalid
    with pytest.raises(ValidationError):
        _ = inp.value([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def test_parameter_matrix_default_value():
    default_value = [1.0, 2.0, 4.0, 5.0, 6.0, 7.0]

    param = QgsProcessingParameterMatrix(
        "Matrix",
        hasFixedNumberRows=True,
        numberRows=3,
        defaultValue=default_value,
    )

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMatrix)

    schema = inp.json_schema()
    print("\ntest_parameter_matrix_no_headers::", schema)

    assert schema["default"] == [[1.0, 2.0], [4.0, 5.0], [6.0, 7.0]]
