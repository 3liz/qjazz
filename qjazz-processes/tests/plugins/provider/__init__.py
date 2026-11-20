from qgis.core import QgsApplication

from .provider import TestAlgorithmProvider


class Test:
    def __init__(self) -> None:
        pass

    def initProcessing(self) -> None:
        reg = QgsApplication.processingRegistry()
        assert reg is not None

        # XXX we *MUST* keep instance of provider
        self._provider = TestAlgorithmProvider()
        reg.addProvider(self._provider)


def classFactory(iface: None) -> Test:
    return Test()
