
from qgis.core import QgsApplication

from .provider import TestAlgorithmProvider


class Test:
    def __init__(self):
        pass

    def initProcessing(self):
        reg = QgsApplication.processingRegistry()

        # XXX we *MUST* keep instance of provider
        self._provider = TestAlgorithmProvider()
        reg.addProvider(self._provider)


def classFactory(iface: None) -> Test:

    return Test()
