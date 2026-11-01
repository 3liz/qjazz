from typing import Annotated

from pydantic import Field

from qgis.core import Qgis, QgsUnitTypes

from qjazz_processes.schemas import input_model_description, ogc


def test_uom_distance_schema():
    # Test distance UOM schema
    for u in Qgis.DistanceUnit:
        if u == Qgis.DistanceUnit.Unknown:
            continue
        assert ogc.UOM.get(QgsUnitTypes.toString(u)) is not None


def test_uom_temporal_schema():
    # Test distance UOM schema
    for u in Qgis.TemporalUnit:
        if u in (Qgis.TemporalUnit.Unknown, Qgis.TemporalUnit.IrregularStep):
            continue
        assert ogc.UOM.get(QgsUnitTypes.toString(u)) is not None


def test_input_model_description():
    """Input description from a model"""
    # No title
    desc = input_model_description(int, title=None, description=None)
    assert desc.title == ""
    assert desc.schema_ == {"type": "integer"}
    assert desc.value_passing == ("byValue",)

    # Optional input with extra schema
    desc = input_model_description(
        Annotated[int, Field(ge=0)],
        title="Count",
        description="A count",
        optional=True,
        max_occurs=3,
        schema_extra=lambda schema: schema.update(format="x-count"),
    )
    assert desc.title == "Count"
    assert desc.min_occurs == 0
    assert desc.max_occurs == 3
    assert desc.schema_ == {"type": "integer", "minimum": 0, "format": "x-count"}

    desc = input_model_description(int, title="T", description=None, schema_extra={"format": "x-int"})
    assert desc.schema_ == {"type": "integer", "format": "x-int"}
