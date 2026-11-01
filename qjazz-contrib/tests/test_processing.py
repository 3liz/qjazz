from qjazz_core.qgis import (
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

    # Only providers registered by plugins: QGIS internal
    # providers ('model', 'script', ...) are not published here
    assert [p.id() for p in s.providers] == ["processing_test"]
