from datetime import datetime
from typing import (
    Literal,
    Optional,
    TypeAlias,
)

from pydantic import BaseModel, Field, TypeAdapter, alias_generators

DateTime = TypeAdapter(datetime)


class BaseResource(
    BaseModel,
    alias_generator=alias_generators.to_camel,
    populate_by_name=True,
    extra="allow",
):
    # Override: force by_alias=True
    def model_dump_json(self, *args, **kwargs) -> str:
        return super().model_dump_json(*args, by_alias=True, exclude_none=True, **kwargs)

    name: str = Field(title="Resource name")


class DirResource(BaseResource):
    is_dir: Literal[True] = True


class FileResource(BaseResource):
    size: Optional[int] = Field(default=None, title="Size in bytes")
    content_type: Optional[str]
    last_modified: Optional[datetime]
    encrypted: bool
    version: Optional[str] = None
    is_dir: Literal[False] = False


ResourceType: TypeAlias = DirResource | FileResource
