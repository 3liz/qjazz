from .config import HandlerConfig, register_protocol_handler  # noqa F401


def register_default_handlers():
    from .file import FileProtocolHandler  # noqa F401
    from .postgresql import PostgresHandler  # noqa F401
    from .geopackage import GeoPackageHandler  # noqa F401

    pass
