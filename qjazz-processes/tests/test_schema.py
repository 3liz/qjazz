from qgis.core import Qgis, QgsUnitTypes

from qjazz_processes.schemas import ogc


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
