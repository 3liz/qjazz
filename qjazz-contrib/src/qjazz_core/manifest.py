"""Build manifest"""

import traceback

from functools import cache
from typing import TYPE_CHECKING, Optional, cast

from pydantic import BaseModel

# Type only import
if TYPE_CHECKING:
    from pathlib import Path


class Manifest(BaseModel):
    commit_id: Optional[str] = None


@cache
def get_manifest() -> Manifest:
    from importlib import resources

    path = cast("Path", resources.files("qjazz_core")).joinpath("manifest.json")
    if path.exists():
        try:
            with path.open() as m:
                return Manifest.model_validate_json(m.read())
        except Exception:
            traceback.print_exc()

    return Manifest()


def short_commit_id() -> Optional[str]:
    short_commit = get_manifest().commit_id
    return short_commit[:12] if short_commit else None
