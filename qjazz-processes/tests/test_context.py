#
# Test processing context
#
from pathlib import Path

from qgis.core import QgsProcessingParameterFileDestination

from qjazz_processes.processing.config import ProcessingConfig
from qjazz_processes.processing.context import ProcessingContext
from qjazz_processes.processing.inputs import InputParameter


def test_context_workdir(qgis_session: ProcessingConfig, tmp_path: Path) -> None:
    """The job folder is located in the context workdir"""
    context = ProcessingContext(tmp_path, qgis_session)
    assert context.workdir == tmp_path.joinpath(context.job_id)

    context.job_id = "test_context_workdir"
    assert context.workdir == tmp_path.joinpath("test_context_workdir")

    # Destination inputs are resolved in the job folder
    param = QgsProcessingParameterFileDestination("OUT", fileFilter="CSV (*.csv)")
    value = InputParameter(param).value("out.csv", context)
    assert value == str(tmp_path.joinpath(context.job_id, "out.csv"))

    # Nothing is created
    assert list(tmp_path.iterdir()) == []
