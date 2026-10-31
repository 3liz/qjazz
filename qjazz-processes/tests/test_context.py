#
# Test processing context
#
from pathlib import Path

import pytest

from qgis.core import QgsProcessingParameterFileDestination

from qjazz_processes.processing.config import ProcessingConfig
from qjazz_processes.processing.context import ProcessingContext
from qjazz_processes.processing.inputs import InputParameter


def test_context_default_config(
    qgis_session: ProcessingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A context without config uses the current directory as workdir"""
    monkeypatch.chdir(tmp_path)

    context = ProcessingContext()
    assert context.workdir == tmp_path.joinpath(context.job_id)

    # Inputs called without context fall back to the default context
    param = QgsProcessingParameterFileDestination("OUT", fileFilter="CSV (*.csv)")
    value = InputParameter(param).value("out.csv")
    assert value == str(tmp_path.joinpath(context.job_id, "out.csv"))

    # Nothing is created
    assert list(tmp_path.iterdir()) == []
