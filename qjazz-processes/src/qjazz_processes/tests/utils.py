from typing import Protocol

from qjazz_core import logger

from qgis.core import QgsProcessingFeedback, QgsProject


class Projects(Protocol):
    def get(self, name: str) -> QgsProject: ...


class Feedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__(False)

    def pushFormattedMessage(_html: str, text: str):
        logger.info(text)

    def setProgressText(self, message: str):
        logger.info("Progress: %s", message)

    def reportError(self, error: str, fatalError: bool = False):
        (logger.critical if fatalError else logger.error)(error)

    def pushInfo(self, info: str) -> None:
        logger.info(info)

    def pushWarning(self, warning: str) -> None:
        logger.warning(warning)

    def pushDebugInfo(self, info: str) -> None:
        logger.debug(info)
