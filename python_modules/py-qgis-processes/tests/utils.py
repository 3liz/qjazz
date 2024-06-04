
from qgis.core import QgsProcessingFeedback

from py_qgis_contrib.core import logger


class FeedBack(QgsProcessingFeedback):

    def __init__(self):
        super().__init__()

    def setProgress(self, progress: float) -> None:
        self._response.update_status(status_percentage=int(progress + 0.5))

    def setProgressText(self, message: str) -> None:
        logger.debug("Progress: %s", message)

    def reportError(self, error: str, fatalError: bool = False):
        (logger.critical if fatalError else logger.error)(error)

    def pushInfo(self, info: str) -> None:
        logger.info(info)

    def pushDebugInfo(self, info: str) -> None:
        logger.debug(info)
