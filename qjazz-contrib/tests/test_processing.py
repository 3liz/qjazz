from qjazz_contrib.core.qgis import (
    PluginType,
    QgisPluginConfig,
    QgisPluginService,
)


def test_processing_plugin(plugindir):
    """Test load processing plugins"""
    config = QgisPluginConfig(
        paths=[plugindir],
    )

    s = QgisPluginService(config)
    s.load_plugins(PluginType.PROCESSING, None)

    providers = list(s.providers)
    assert len(providers) == 3
    assert "processing_test" in set(p.id() for p in providers)
