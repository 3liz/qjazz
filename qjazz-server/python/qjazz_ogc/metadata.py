from datetime import datetime
from typing import Optional

from qgis.core import (
    QgsAbstractMetadataBase,
)
from qgis.PyQt.QtCore import QDateTime

from .stac import links


def Keywords(md: QgsAbstractMetadataBase) -> list[str]:
    return md.categories()


def Links(md: QgsAbstractMetadataBase) -> list[links.Link]:
    return [
        links.Link(
            href=link.url(),
            media_type=link.mimeType(),
            title=link.name(),
            description=link.description(),
            rel="related",
        )
        for link in md.links()
    ]


def DateTime(dt: QDateTime) -> Optional[datetime]:
    return dt.toPyDateTime() if dt.isValid() else None
