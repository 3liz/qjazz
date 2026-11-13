"""File protocol handler"""

import urllib.parse

from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlsplit, urlunsplit

from qjazz_core import componentmanager

from ..resources import (
    ResourceObject,
    ResourceReader,
)
from .config import StorageHandler

Url = urllib.parse.SplitResult


@componentmanager.register_factory("@3liz.org/cache/storage-handler;1?scheme=file")
class FileStorageHandler(StorageHandler):
    """File storage"""

    def __init__(self):
        pass

    def resolve_uri(self, uri: Url) -> str:
        """Override"""
        return uri.path

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:
        """Override"""
        if isinstance(url, str):
            url = urlsplit(url)
        relpath = Path(url.path).relative_to(rooturl.path)
        return str(Path(location).joinpath(relpath))

    #
    # Implement the ResourceStore Protocol
    #

    def get_resource(self, uri: Url, name: Optional[str] = None) -> Optional[ResourceReader]:
        """Return a resource reader for the given uri"""

        path = Path(uri.path)
        if name:
            path = path.joinpath(name)

        try:
            stat = path.stat()
        except FileNotFoundError:
            return None

        fp = path.open("rb")
        return ResourceReader(
            read=fp.read,
            close=fp.close,
            size=stat.st_size,
            content_type=None,
            uri=urlunsplit(uri),
        )

    def list_resources(self, uri: Url, subpath: Optional[str] = None) -> Iterator[ResourceObject]:
        """List resources"""

        root = Path(uri.path)
        path = root.joinpath(subpath) if subpath else root

        if not path.is_dir():
            return

        for res in path.iterdir():
            st = res.stat()
            yield ResourceObject(
                name=str(res.relative_to(root)),
                size=st.st_size,
                content_type=None,
                last_modified=datetime.fromtimestamp(st.st_mtime),
                is_dir=res.is_dir(),
            )
