#
# Plugins inspection
#
from multiprocessing.connection import Connection

from py_qgis_contrib.core.qgis import QgisPluginService

from . import messages as _m


def inspect_plugins(
    conn: Connection,
    s: QgisPluginService,
):
    count = s.num_plugins
    _m.send_reply(conn, count)
    if count:
        try:
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
        except Exception:
            raise
        else:
            # EOT
            _m.send_reply(conn, None)
