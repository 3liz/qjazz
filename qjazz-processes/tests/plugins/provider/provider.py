"""Test processing Provider"""

import traceback

from qgis.core import QgsProcessingProvider

from .TestClipRasterLayer import TestClipRasterLayer
from .TestCopyLayer import TestCopyLayer
from .TestFileDestination import TestFileDestination
from .TestInputFile import TestInputFile
from .TestInputGeometry import TestInputGeometry
from .TestInputMultiLayer import TestInputMultiLayer
from .TestInputRasterLayer import TestInputRasterLayer
from .TestLongProcess import TestLongProcess
from .TestMultiOptionValue import TestMultiOptionValue
from .TestOptionValue import TestOptionValue
from .TestOutputFile import TestOutputFile
from .TestOutputVectorLayer import TestOutputVectorLayer
from .TestRaiseError import TestRaiseError
from .TestSimpleBuffer import TestSimpleBuffer
from .TestSimpleValue import TestSimpleValue
from .TestUltimateQuestion import TestUltimateQuestion


class TestAlgorithmProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def id(self):
        return "processes_test"

    def name(self):
        return "Proceses Test"

    def loadAlgorithms(self):
        algs = [
            TestSimpleValue,
            TestOptionValue,
            TestMultiOptionValue,
            TestCopyLayer,
            TestFileDestination,
            TestSimpleBuffer,
            TestInputRasterLayer,
            TestRaiseError,
            TestClipRasterLayer,
            TestInputMultiLayer,
            TestLongProcess,
            TestInputFile,
            TestOutputVectorLayer,
            TestOutputFile,
            TestInputGeometry,
            TestUltimateQuestion,
        ]
        try:
            for Alg in algs:
                self.addAlgorithm(Alg())
        except:
            # Make sure that error is dumped somewhere
            traceback.format_exc()
            raise


class DummyAlgorithmProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def id(self):
        return "proceses_dummy_test"

    def name(self):
        return "Processes Dummy Test"

    def loadAlgorithms(self):
        pass
