import zipfile

from itertools import chain
from pathlib import Path

from qgis.core import QgsProcessingFeedback

from qjazz_processes.processing.prelude import (
    ProcessingContext,
)

from .formats import WfsOutputDefn


def archive_files(
    output_file: Path,
    format_defn: WfsOutputDefn,
    feedback: QgsProcessingFeedback,
    context: ProcessingContext,
) -> Path:
    """Archive output_file and auxiliaries"""
    archive = output_file.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in chain(
            (output_file,),
            *(context.workdir.glob(aux) for aux in format_defn.auxiliary_files),
        ):
            zf.write(file, arcname=file.name)

    return archive
