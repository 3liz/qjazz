
import sys
from qgis.core import Qgis, QgsMessageLog


def serverClassFactory(serverIface):  # pylint: disable=invalid-name
    """Load wfsOutputExtensionServer class from file wfsOutputExtension.

    :param iface: A QGIS Server interface instance.
    :type iface: QgsServerInterface
    """
    #
    return Foo(serverIface)

class Foo:
    def __init__(self, iface):
        QgsMessageLog.logMessage("SUCCESS - plugin foo  initialized")

        # Test that module is marked
        pkg = sys.modules['foo']
        assert pkg._is_qjazz_server

    
