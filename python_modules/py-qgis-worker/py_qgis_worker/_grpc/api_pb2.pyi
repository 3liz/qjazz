from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PingRequest(_message.Message):
    __slots__ = ["echo"]
    ECHO_FIELD_NUMBER: _ClassVar[int]
    echo: str
    def __init__(self, echo: _Optional[str] = ...) -> None: ...

class PingReply(_message.Message):
    __slots__ = ["echo"]
    ECHO_FIELD_NUMBER: _ClassVar[int]
    echo: str
    def __init__(self, echo: _Optional[str] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = []
    def __init__(self) -> None: ...

class ResponseChunk(_message.Message):
    __slots__ = ["chunk"]
    CHUNK_FIELD_NUMBER: _ClassVar[int]
    chunk: bytes
    def __init__(self, chunk: _Optional[bytes] = ...) -> None: ...

class OwsRequest(_message.Message):
    __slots__ = ["service", "request", "target", "version", "url", "direct", "options"]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    DIRECT_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    service: str
    request: str
    target: str
    version: str
    url: str
    direct: bool
    options: str
    def __init__(self, service: _Optional[str] = ..., request: _Optional[str] = ..., target: _Optional[str] = ..., version: _Optional[str] = ..., url: _Optional[str] = ..., direct: bool = ..., options: _Optional[str] = ...) -> None: ...

class GenericRequest(_message.Message):
    __slots__ = ["url", "method", "data", "target", "version", "direct"]
    URL_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DIRECT_FIELD_NUMBER: _ClassVar[int]
    url: str
    method: str
    data: bytes
    target: str
    version: str
    direct: bool
    def __init__(self, url: _Optional[str] = ..., method: _Optional[str] = ..., data: _Optional[bytes] = ..., target: _Optional[str] = ..., version: _Optional[str] = ..., direct: bool = ...) -> None: ...

class CheckoutRequest(_message.Message):
    __slots__ = ["uri", "pull"]
    URI_FIELD_NUMBER: _ClassVar[int]
    PULL_FIELD_NUMBER: _ClassVar[int]
    uri: str
    pull: bool
    def __init__(self, uri: _Optional[str] = ..., pull: bool = ...) -> None: ...

class CacheInfo(_message.Message):
    __slots__ = ["uri", "status", "in_cache", "name", "storage", "last_modified", "saved_version", "debug_metadata"]
    class DebugMetadataEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    URI_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    IN_CACHE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STORAGE_FIELD_NUMBER: _ClassVar[int]
    LAST_MODIFIED_FIELD_NUMBER: _ClassVar[int]
    SAVED_VERSION_FIELD_NUMBER: _ClassVar[int]
    DEBUG_METADATA_FIELD_NUMBER: _ClassVar[int]
    uri: str
    status: str
    in_cache: bool
    name: str
    storage: str
    last_modified: str
    saved_version: str
    debug_metadata: _containers.ScalarMap[str, int]
    def __init__(self, uri: _Optional[str] = ..., status: _Optional[str] = ..., in_cache: bool = ..., name: _Optional[str] = ..., storage: _Optional[str] = ..., last_modified: _Optional[str] = ..., saved_version: _Optional[str] = ..., debug_metadata: _Optional[_Mapping[str, int]] = ...) -> None: ...

class DropRequest(_message.Message):
    __slots__ = ["uri"]
    URI_FIELD_NUMBER: _ClassVar[int]
    uri: str
    def __init__(self, uri: _Optional[str] = ...) -> None: ...

class ListRequest(_message.Message):
    __slots__ = ["status_filter"]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    status_filter: str
    def __init__(self, status_filter: _Optional[str] = ...) -> None: ...
