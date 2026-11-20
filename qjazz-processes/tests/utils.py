from typing import Protocol

from qjazz_core import logger

from qgis.core import QgsProcessingFeedback, QgsProject


class Projects(Protocol):
    def get(self, name: str) -> QgsProject: ...


class Feedback(QgsProcessingFeedback):
    def __init__(self) -> None:
        super().__init__(False)

    def pushFormattedMessage(self, html: str | None, text: str | None) -> None:
        logger.info(str(text))

    def setProgressText(self, message: str | None) -> None:
        logger.info("Progress: %s", str(message))

    def reportError(self, error: str | None, fatalError: bool = False) -> None:
        (logger.critical if fatalError else logger.error)(str(error))

    def pushInfo(self, info: str | None) -> None:
        logger.info(str(info))

    def pushWarning(self, warning: str | None) -> None:
        logger.warning(str(warning))

    def pushDebugInfo(self, info: str | None) -> None:
        logger.debug(str(info))
