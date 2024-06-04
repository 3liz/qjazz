

from qgis.core import (
    QgsApplication,
)

from py_qgis_contrib.core.qgis import QgisPluginService
from py_qgis_processes.processing.config import ProcessingConfig


def test_plugins_provider(
    qgis_session: ProcessingConfig,
    plugins: QgisPluginService,
):
    registry = QgsApplication.processingRegistry()

    # Output published providers
    print("\ntest_plugins_provider:providers", [p.id() for p in plugins.providers])

    models = registry.providerById("model")
    assert models is not None

    # Check models have been imported
    algs = models.algorithms()
    assert len(algs) > 0

    print("test_plugins_provider:models", [a.id() for a in models.algorithms()])

    scripts = registry.providerById("script")
    assert scripts is not None

    # Check scripts have been imported
    algs = scripts.algorithms()
    assert len(algs) > 0

    print("test_plugins_provider:scripts", [a.id() for a in scripts.algorithms()])

    # Check provider
    provider = registry.providerById("processes_test")
    assert provider is not None

    print("test_plugins_provider:provider", [a.id() for a in provider.algorithms()])

    # Check that models and scripts are published:
    assert 'model' in plugins._providers
    assert 'script' in plugins._providers
