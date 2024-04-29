
from qgis.core import Qgis, QgsUnitTypes

from py_qgis_processes_schemas import ogc


def test_uom_schema():

    # Test distance UOM schema
    for u in Qgis.DistanceUnit:
        if u == Qgis.DistanceUnit.Unknown:
            continue
        assert ogc.UOM.get(QgsUnitTypes.toString(u)) is not None
