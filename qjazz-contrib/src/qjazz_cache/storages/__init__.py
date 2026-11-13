from collections.abc import Mapping

from .config import (
    StorageHandler,
    StorageHandlerConfig,
    register_storage_handler,
)


def register_storage_handlers(handlers: Mapping[str, StorageHandlerConfig] | None = None):
    # Import default handler(s)
    from .file import FileStorageHandler  # noqa F401

    if handlers is not None:
        for scheme, conf in handlers.items():
            register_storage_handler(scheme, conf)


def get_storage_handler(scheme: str) -> StorageHandler:
    """Find protocol handler for the given scheme"""
    from qjazz_core import componentmanager
    return componentmanager.get_service(
        f"@3liz.org/cache/storage-handler;1?scheme={scheme or 'file'}",
    )


