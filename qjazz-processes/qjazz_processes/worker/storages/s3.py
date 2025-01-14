"""
S3 object storage support
"""

import mimetypes
import os
import traceback

from datetime import timedelta
from pathlib import Path
from typing import (
    Iterator,
    Optional,
)

from minio import Minio, commonconfig
from minio.deleteobjects import DeleteObject
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
from pydantic import Field, FilePath, SecretStr

from qjazz_contrib.core import logger
from qjazz_contrib.core.config import ConfigSettings

from ..models import Link


class S3Config(ConfigSettings, env_prefix="conf_s3_"):
    endpoint: str
    access_key: str
    secret_key: SecretStr
    region: Optional[str] = None

    cafile: Optional[FilePath] = None
    secure: bool = True
    check_cert: bool = True

    bucket_name: str = Field(title="Bucket name")
    create_bucket: bool = Field(
        True,
        title="Create bucket",
        description="Create bucket if it does not exists",
    )

    expiration_days: int = Field(
        default=1,
        ge=1,
        title="Expiration days",
        description="Maximum retention in days for objects",
    )


def _create_bucket(client: Minio, conf: S3Config):
    """ Create the storage bucket
    """
    # Create the bucket for the service
    if not client.bucket_exists(conf.bucket_name):
        logger.info("[S3] Creating bucket '%s' on '%s'", conf.bucket_name, conf.endpoint)
        client.make_bucket(conf.bucket_name, location=conf.region)
        client.set_bucket_lifecycle(
            conf.bucket_name,
            config=LifecycleConfig(
                [
                    Rule(
                        commonconfig.ENABLED,
                        rule_filter=commonconfig.Filter(prefix=""),
                        rule_id="global_expiration_rule",
                        expiration=Expiration(days=conf.expiration_days),
                    ),
                ],
            ),
        )


class S3Storage:
    """ S3 object Storage support
    """

    Config = S3Config

    def __init__(self, conf: S3Config):
        self._conf = conf
        self._client: Minio | None = None

        if self._conf.create_bucket:
            _create_bucket(self.client, self._conf)

    @property
    def bucket(self) -> str:
        return self._conf.bucket_name

    @property
    def client(self) -> Minio:
        """ Lazily create client
        """
        if not self._client:
            if self._conf.cafile:
                os.environ["SSL_CERT_FILE"] = str(self._conf.cafile)

            self._client = Minio(
                self._conf.endpoint,
                access_key=self._conf.access_key,
                secret_key=self._conf.secret_key.get_secret_value(),
                secure=self._conf.secure,
                cert_check=self._conf.check_cert,
                region=self._conf.region,
            )
        return self._client

    def before_create_process(self):
        """ Called each time just before a process
            is created. Minio doesn't play well with fork
        """
        # Invalidate client
        self._client = None

    def download_url(
        self,
        job_id: str,
        resource: str,
        *,
        workdir: Path,
        expires: int = 3600,
    ) -> Link:
        """ Returns an effective download url for the given resource
        """
        # Get object info
        object_name = f"{job_id}/{resource}"

        stat = self.client.stat_object(self.bucket, object_name)

        # Create presigned url
        url = self.client.presigned_get_object(
            self.bucket,
            f"{job_id}/{resource}",
            expires=timedelta(seconds=expires),
        )

        return Link(
            href=url,
            mime_type=stat.content_type,
            length=stat.size,
            title=resource,
        )

    def move_files(
        self,
        job_id: str,
        *,
        workdir: Path,
        files: Iterator[Path],
    ):
        for file in files:
            #
            # Get object name
            #
            if file.is_absolute():
                if not file.is_relative_to(workdir):
                    logger.warning("Cannot transfer non-relative file %s", file)
                    continue
                object_name = str(file.relative_to(workdir))
            else:
                object_name = str(file)

            content_type = mimetypes.types_map.get(file.suffix)

            stat = file.stat()

            logger.debug("[S3] Transferring '%s' (size=%s)", file, stat.st_size)
            with file.open('rb') as reader:
                self.client.put_object(
                    self.bucket,
                    object_name,
                    reader,
                    content_type=content_type or "application/octet-stream",
                    length=stat.st_size,
                )
            # Remove file from its original location
            try:
                logger.debug("[S3] Deleting file '%s'", file)
                file.unlink()
            except Exception:
                logger.error(
                    "[S3] An error occured while deleting %s:\n%s",
                    file,
                    traceback.format_exc(),
                )

    def remove(self, job_id: str, *, workdir: Path):
        """ Delete all resources in prefix 'job_id' """
        logger.info("[S3] Deleting objects in %s/%s", self.bucket, job_id)
        client = self.client
        delete_object_list = map(
            lambda x: DeleteObject(x.object_name),
            client.list_objects(self.bucket, f"{job_id}/", recursive=True),
        )

        errors = client.remove_objects(self.bucket, delete_object_list)
        for error in errors:
            logger.error("[S3] Error deleting object: %s", error)
