import urllib.parse

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    Callable,
    Iterator,
    Optional,
    Protocol,
    runtime_checkable,
)

Url = urllib.parse.SplitResult


@dataclass(frozen=True)
class ResourceReader:
    read: Callable[..., bytes]
    close: Callable[[], None]
    size: int
    content_type: Optional[str]
    uri: str


@dataclass(frozen=True)
class ResourceObject:
    name: str
    size: int
    content_type: Optional[str]
    last_modified: Optional[datetime]
    is_dir: bool


@runtime_checkable
class ResourceStore(Protocol):
    def get_resource(self, uri: Url, name: Optional[str] = None) -> Optional[ResourceReader]:
        """Return a resource download url for the given uri"""
        ...

    def list_resources(self, uri: Url, prefix: Optional[str] = None) -> Iterator[ResourceObject]:
        """Return a list of resources at the given url"""
        ...


@runtime_checkable
class RemoteResources(Protocol):
    def fget_resource(self, uri: Url, name: Optional[str], dest: Path):
        """Copy a remote file to a local destination"""
        ...
