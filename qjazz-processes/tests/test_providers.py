#
# Test published processing providers
#
import pytest

from qjazz_core.qgis import QgisPluginService

from qjazz_processes.processing.prelude import ProcessAlgorithm


def _published(exposed_providers: tuple[str, ...]) -> set[str]:
    return {
        alg.ident.split(":")[0] for alg in ProcessAlgorithm.algorithms(exposed_providers=exposed_providers)
    }


@pytest.mark.parametrize(
    "exposed_providers,expected",
    [
        # Providers registered by plugins are always published
        ((), {"processes_test"}),
        (("model",), {"processes_test", "model"}),
        # Default configuration
        (("script", "model"), {"processes_test", "model", "script"}),
        (("native",), {"processes_test", "native"}),
        # Unknown providers are ignored
        (("foobar",), {"processes_test"}),
    ],
)
def test_published_providers(
    plugins: QgisPluginService, exposed_providers: tuple[str, ...], expected: set[str]
):
    assert _published(exposed_providers) == expected
