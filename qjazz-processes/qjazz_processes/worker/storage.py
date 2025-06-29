from abc import abstractmethod
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Iterable,
    Optional,
    Protocol,
    Self,
    runtime_checkable,
)

from pydantic import (
    BaseModel,
    ImportString,
    WithJsonSchema,
    model_validator,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.config import ConfigBase
from qjazz_contrib.core.models import Field

from .models import Link

# Enable type checking from Protocol
# This allows for validating Storage instances


@runtime_checkable
class Storage(Protocol):
    @abstractmethod
    def download_url(
        self,
        job_id: str,
        resource: str,
        *,
        workdir: Path,
        expires: Optional[int],
    ) -> Link:
        """Returns a download reference for the given resource"""
        ...

    @abstractmethod
    def move_files(
        self,
        job_id: str,
        *,
        workdir: Path,
        files: Iterable[Path],
    ):
        """Move files to storage"""
        ...

    def before_create_process(self):
        """Called before each time a new process is created
        for cleaning resource that don't play well with
        fork
        """
        pass

    def remove(self, job_id: str, *, workdir: Path):
        """Clean resources"""
        pass


class StorageConfig(ConfigBase):
    """Configure storage for processing data"""

    storage_class: Annotated[
        ImportString,
        WithJsonSchema({"type": "string"}),
        Field(
            default="qjazz_processes.worker.storages.local.LocalStorage",
            validate_default=True,
            title="Storage module",
            description="""
            The module implementing storage accesses for
            job's files.
            """,
        ),
    ]
    config: dict[str, Any] = Field({})

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        klass = self.storage_class
        if not issubclass(klass, Storage):
            raise ValueError(f"{klass} does not support Storage protocol")

        self._storage_conf: BaseModel | None = None
        if hasattr(klass, "Config") and issubclass(klass.Config, BaseModel):
            self._storage_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self) -> Storage:
        """Returns instance of storage configuration"""
        logger.info("Initializing storage '%s'", str(self.storage_class))
        if self._storage_conf:
            return self.storage_class(self._storage_conf)
        else:
            return self.storage_class()
