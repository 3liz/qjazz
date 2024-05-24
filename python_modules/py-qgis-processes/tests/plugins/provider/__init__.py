
from qgis.core import QgsApplication

from .provider import TestAlgorithmProvider


class Test:
    def __init__(self):
        pass

    def initProcessing(self):
        reg = QgsApplication.processingRegistry()
        reg.addProvider(TestAlgorithmProvider())


def ClassFactory(iface: None) -> Test:

    return Test()
