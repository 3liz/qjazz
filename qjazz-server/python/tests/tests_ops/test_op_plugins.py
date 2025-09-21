

from qjazz_core.qgis import QgisPluginService

from qjazz_rpc import messages, op_plugins
from qjazz_rpc.worker import Server

from .connection import Connection


def test_op_plugins(qgis_server: Server):

    conn = Connection()
    plugin_s = QgisPluginService.get_service()

    op_plugins.inspect_plugins(conn, plugin_s)

    count = 0
    for resp in conn.stream():
        print("\n::test_op_plugins::", resp)
        messages.PluginInfo.model_validate(resp)
        count += 1

    assert count >= 2
