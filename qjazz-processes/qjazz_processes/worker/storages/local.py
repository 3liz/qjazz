import mimetypes

from pathlib import Path
from typing import (
    Iterator,
    Optional,
)

from ..models import Link
from ..storage import Storage


class LocalStorage(Storage):
    """Local filesystem storage class"""

    def download_url(
        self,
        job_id: str,
        resource: str,
        *,
        workdir: Path,
        expires: Optional[int],
    ) -> Link:
        """Returns an effective download url for the given resource"""
        path = workdir.joinpath(job_id, resource)
        if not path.exists():
            raise FileNotFoundError(f"{path}")

        content_type = mimetypes.types_map.get(path.suffix)
        size = path.stat().st_size
        return Link(
            href=path.as_uri(),
            mime_type=content_type or "application/octet-stream",
            length=size,
            title=path.name,
        )

    def move_files(
        self,
        job_id: str,
        *,
        workdir: Path,
        files: Iterator[Path],
    ):
        # No-op
        pass
