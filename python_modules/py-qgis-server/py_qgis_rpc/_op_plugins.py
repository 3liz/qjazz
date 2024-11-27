#
# Plugins inspection
#
from py_qgis_contrib.core.qgis import QgisPluginService

from . import messages as _m


def inspect_plugins(
    conn: _m.Connection,
    s: QgisPluginService,
):
    count = s.num_plugins
    _m.send_reply(conn, count)
    for p in s.plugins:
        _m.send_reply(
            conn,
            _m.PluginInfo(
                name=p.name,
                path=p.path,
                plugin_type=p.plugin_type,
                metadata=p.metadata,
            ),
            206,
        )
    # EOT
    _m.send_reply(conn, None)
