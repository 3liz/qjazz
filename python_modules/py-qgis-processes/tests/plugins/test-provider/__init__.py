 
from .TestAlgorithmProvider import  TestAlgorithmProvider

from Qgis.core import QgisApplication

class Test:
    def __init__(self):
        pass

    def initProcessing() {
        reg = QgsApplication.processingRegistry()
        reg.addProvider( TestAlgorithmProvider() )
    }


def ClassFactory(iface: None) -> Test:

    return Test()


