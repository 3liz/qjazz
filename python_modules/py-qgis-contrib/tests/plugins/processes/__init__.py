from qgis.core import QgsApplication
from .TestAlgorithmProvider import TestAlgorithmProvider


def classFactory(_iface):
    return Plugin()


class Plugin:
    def __init__(self):
        pass

    def initGui(self):
        pass

    def initProcessing(self):
        self.provider = TestAlgorithmProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)
