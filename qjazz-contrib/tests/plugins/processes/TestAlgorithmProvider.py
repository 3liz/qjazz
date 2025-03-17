"""Test processing Provider"""

from qgis.core import QgsProcessingProvider

from .TestUltimateQuestion import TestUltimateQuestion


class TestAlgorithmProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def id(self):
        return "processing_test"

    def name(self):
        return "Processing Test"

    def loadAlgorithms(self):
        algs = (TestUltimateQuestion(),)

        for a in algs:
            self.addAlgorithm(a)
