from datetime import datetime
from typing import (
    Literal,
    TypeAlias,
)

from pydantic import BaseModel, Field, TypeAdapter, alias_generators

from qjazz_core.models import JsonDict, Option, cleanup_schema

DateTime = TypeAdapter(datetime)


class BaseResource(
    BaseModel,
    alias_generator=alias_generators.to_camel,
    populate_by_name=True,
    extra="allow",
):
    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> JsonDict:
        schema = super(BaseResource, cls).model_json_schema(*args, **kwargs)
        cleanup_schema(schema)
        return schema

    # Override: force by_alias=True
    def model_dump_json(self, *args, **kwargs) -> str:
        return super().model_dump_json(*args, by_alias=True, exclude_none=True, **kwargs)

    name: str = Field(title="Resource name")


class DirResource(BaseResource):
    is_dir: Literal[True] = True


class FileResource(BaseResource):
    size: Option[int] = Field(default=None, title="Size in bytes")
    content_type: Option[str]
    last_modified: Option[datetime]
    encrypted: bool
    version: Option[str] = None
    is_dir: Literal[False] = False


ResourceType: TypeAlias = DirResource | FileResource
