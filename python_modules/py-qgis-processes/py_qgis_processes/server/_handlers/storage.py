
from pathlib import Path

from aiohttp import web
from pydantic import (
    AnyUrl,
    ByteSize,
)
from typing_extensions import (
    Self,
    Sequence,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_precondition

from ...schemas import Link as LinkAny
from ..utils import stream_from
from .protos import (
    ErrorResponse,
    HandlerProto,
    Link,
    ProcessFiles,
    make_link,
    swagger,
)

#
# Handler
#


class FileLink(LinkAny):
    display_size: str

    @classmethod
    def from_link(cls, link: LinkAny) -> Self:
        size = cast(int, link.length)
        return cls(
            href=link.href,
            length=size,
            mime_type=link.mime_type,
            title=link.title,
            display_size=ByteSize(size).human_readable(decimal=True),
        )


@swagger.model
class FilesResponse(swagger.JsonModel):
    files: Sequence[FileLink]
    links: Sequence[Link]

    @classmethod
    def from_files(cls, files: ProcessFiles, links: Sequence[Link]) -> Self:
        return cls(
            links=links,
            files=[FileLink.from_link(link) for link in files.links],
        )


class Storage(HandlerProto):

    async def job_files(self, request: web.Request) -> web.Response:
        """
        summary: Get Job process execution files
        description: |
            Returns the job processe execution files
        parameters:
            - in: path
              name: JobId
              schema:
                type: string
              required: true
              description: Job id
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job log
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/FilesResponse'
            "404":
                description: Job not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        job_id = request.match_info['JobId']

        files = await self._executor.files(
            job_id,
            realm=self._jobrealm.job_realm(request),
            timeout=self._timeout,
        )

        if not files:
            return ErrorResponse.response(404, "Job not found", {"jobId": job_id})

        location = self.format_path(request, f"/jobs/{job_id}/files")

        return web.Response(
            content_type="application/json",
            text=FilesResponse.from_files(
                files=files,
                links=[
                    make_link(
                        request,
                        path=location,
                        rel="self",
                        title="Job execution log",
                    ),
                ],
            ).model_dump_json(),
        )

    async def job_download(self, request: web.Request) -> web.StreamResponse:
        """
        summary: Get Job process execution files
        description: |
            Returns the job processe execution files
        parameters:
            - in: path
              name: JobId
              schema:
                type: string
              required: true
              description: Job id
            - in: path
              name: Resource
              schema:
                type: string
              required: true
              description: Resource path
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job log
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/FilesResponse'
            "404":
                description: Job or resource not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        job_id = request.match_info['JobId']
        resource = request.match_info['Resource']

        link = await self._executor.download_url(
            job_id,
            resource=resource,
            realm=self._jobrealm.job_realm(request),
            timeout=self._timeout,
            expiration=self._storage.download_url_expiration,
        )

        if not link:
            return ErrorResponse.response(
                404,
                "Job or resource not found",
                {"jobId": job_id, "resource": resource},
            )

        headers = {'Content-Length': f"{link.length}"}

        if request.method == 'HEAD':
            return web.Response(content_type=link.mime_type, headers=headers)

        response = web.StreamResponse(headers=headers)
        await response.prepare(request)

        url = AnyUrl(link.href)

        match url.scheme:
            case 'file':
                import aiofiles
                # Local file storage
                path = Path(str(url.path))
                assert_precondition(path.is_file())
                try:
                    async with aiofiles.open(path, mode='+rb') as fh:
                        chunk = await fh.read(self._storage.chunksize)
                        while chunk:
                            await response.write(chunk)
                            chunk = await fh.read(self._storage.chunksize)
                except OSError as err:
                    logger.error("Connection cancelled: %s", err)
                    raise
            case 'http':
                if not self._storage.allow_insecure_connection:
                    logger.error("Storage service '%s' returned unauthorized insecure protocol")
                    raise web.HTTPForbidden()
                await stream_from(link.href, response, self._storage.chunksize)
            case 'https':
                await stream_from(
                    link.href,
                    response,
                    self._storage.chunksize,
                    self._storage.ssl.create_ssl_client_context(),
                )
            case _:
                logger.error("Unsupported storage url scheme %s", url.scheme)
                raise web.HTTPBadGateway()

        await response.write_eof()
        return response
