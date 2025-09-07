"""Store handler

Acces to storage linked to identity:
    * Push and pull resources
    * Enable encryption

Workers will have access to this storage
"""

import traceback

from typing import (
    AsyncIterator,
    Callable,
    ContextManager,
    Literal,
    Optional,
)

import qjazz_store as store

from aiohttp import web
from pydantic import Field, TypeAdapter
from qjazz_core import logger
from qjazz_core.utils import to_rfc822
from qjazz_store.models import ResourceType

from ...schemas import JsonModel
from ..models import BoolParam
from .protos import (
    ErrorResponse,
    HandlerProto,
    Link,
    make_link,
    swagger,
    validate_param,
)

swagger.model(TypeAdapter(ResourceType), name="ResourceType")


def checksum_filter(stream: AsyncIterator[bytes]) -> tuple[AsyncIterator[bytes], Callable[[], str]]:
    """Compute checksum"""
    import hashlib

    h = hashlib.sha256()

    async def _wrapper() -> AsyncIterator[bytes]:
        async for chunk in stream:
            h.update(chunk)
            yield chunk

    return _wrapper(), lambda: h.hexdigest()


@swagger.model
class ResourceList(JsonModel):
    resources: list[ResourceType]
    links: list[Link] = Field(default=[])


@swagger.model
class DeleteResponse(JsonModel):
    resource: str
    status: Literal["deleted"] = "deleted"
    service: str
    role: str


def handle_store_error(err: store.StoreError, request: web.Request) -> web.Response:
    logger.error(
        "%s\nStorace operation failed with error: %s",
        traceback.format_exc(),
        err.status_code,
    )

    if err.status_code == 404:
        resp = ErrorResponse.response(404, "Store resource not found", details=request.path)
    else:
        ErrorResponse.raises(web.HTTPBadGateway, message="Store backend error")

    return resp


class Store(HandlerProto):
    async def list_store(self, request: web.Request) -> web.Response:
        """
        summary: List stored objects"
        description: |
            Returns the list of stored objects
            for service and identity
        parameters:
            - in: query
              name: service
              schema:
                type: string
              required: false
              description: |
                The service requested
                If not set, the default behavior is to return
                the first service in the configured service list
            - in query:
              name: prefix:
              schema:
                type: string
              description: Start prefix for object's name
              required: false
            - in query:
              name: recurse
              schema:
                type boolean
              description: List recursively
        tags: store
        responses:
            "200":
               description: The resource list
               content:
                 application/json:
                    schema:
                        $ref: "#definitions/ResourceList
        """
        service = self.get_service(request)
        identity = self.get_identity(request)

        prefix = request.query.get("prefix")
        recurse = validate_param(BoolParam, request, "recurse", False)

        creds = await self.store_creds()

        try:
            resources = await store.list_store(
                creds,
                service=service,
                identity=identity,
                prefix=prefix,
                recurse=recurse,
            )
        except store.StoreError as err:
            return handle_store_error(err, request)

        for res in resources:
            res.links = [  # type: ignore [union-attr]
                make_link(
                    request,
                    rel="resource",
                    path=self.format_path(
                        request,
                        f"/store/{identity}/{res.name}",
                        service,
                    ),
                    title="Get resource",
                ),
            ]

        return web.Response(
            content_type="application/json",
            text=ResourceList(
                resources=resources,
                links=[
                    make_link(
                        request,
                        path=self.format_path(
                            request,
                            f"/store/{identity}/",
                            service,
                        ),
                        rel="self",
                        title="Resource list",
                    ),
                ],
            ).model_dump_json(),
        )

    async def get_store(self, request: web.Request) -> web.StreamResponse:
        """
        summary: Get stored object
        description: |
            Download a stored object
        parameters:
            - in: query
              name: service
              schema:
                type: string
              required: true
              description: service name
            - in: path
              name: Name
              schema:
                type: string
              required: true
              description: Object path
        tags:
          - storage
        responses:
            "200":
                description: Returns the resource data stream
                content:
                    application/octet-stream:
                        schema:
                            type: string
                            format: binary
            "404":
                description: The resource does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        service = self.get_service(request)
        identity = self.get_identity(request)

        name = request.match_info["Name"]

        client = store.store_client(await self.store_creds())

        res = await store.stat_store(
            client,
            name,
            service=service,
            identity=identity,
        )

        headers = {}
        if res.content_type:
            headers["Content-Type"] = res.content_type
        if res.size:
            headers["Content-Length"] = str(res.size)
        if res.last_modified:
            headers["Last-Modified"] = to_rfc822(res.last_modified.timestamp())

        headers["QJazz-Store-Type"] = "encrypted" if res.encrypted else "plain"

        part_size = 1024 * 1024

        resp: web.StreamResponse

        try:
            with self.read_store(
                client,
                service=service,
                identity=identity,
                part_size=part_size,
                decode=res.encrypted,
            ) as get:
                obj = store.Object(name=name)
                if request.method == "HEAD":
                    resp = web.Response(status=200, headers=headers)
                else:
                    # Stream response
                    resp = web.StreamResponse(
                        status=200,
                        reason="OK",
                        headers=headers,
                    )
                    await resp.prepare(request)
                    async for chunk in get(obj):
                        await resp.write(chunk)
                    await resp.write_eof()
        except store.StoreError as err:
            return handle_store_error(err, request)

        return resp

    async def put_store(self, request: web.Request) -> web.Response:
        """
        summary: Upload data
        description: |
            Upload data to storage
        parameters:
            - in: path
              name: Name
              schema:
                type: string
              required: true
              description: Object path
            - in: query
              name: service
              schema:
                type: string
              required: true
              description: service name
            - in: query
              name: encrypt
              schema:
                type: boolean
              required: false
              description: encrypt data
        tags:
          - storage
        requestBody:
            required: true
            description: |-
                An execution request specifying any inputs for the process to execute,
                and optionally to select specific outputs.
            content:
                application/octet-stream:
                    schema:
                        type: string
                        format: binary
        responses:
            "200":
                description: The resource description
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ResourceType'
        """
        service = self.get_service(request)
        identity = self.get_identity(request)

        name = request.match_info["Name"]

        encrypt = validate_param(BoolParam, request, "encrypt", False)

        headers = request.headers
        content_type = headers.get("Content-Type")
        content_length = headers.get("Content-Length")

        obj = store.Object(
            name=name,
            content_type=content_type,
            size=int(content_length) if content_length else None,
        )

        client = store.store_client(await self.store_creds())

        try:
            # Create the bucket if it does not exists
            await store.create_store(client, service=service)

            with self.write_store(
                client,
                service=service,
                identity=identity,
                encode=encrypt,
            ) as put:
                astream, checksum = checksum_filter(request.content.iter_chunked(1024 * 1024))
                res = await put(obj, astream)

            digest = f"sha256:{checksum()}"
            link = make_link(
                request,
                path=self.format_path(
                    request,
                    f"/store/{identity}/{res.name}",
                    service,
                ),
                rel="resource",
            )

            res.digest = digest  # type: ignore [attr-defined]
            res.links = [link]  # type: ignore [attr-defined]

        except store.StoreError as err:
            return handle_store_error(err, request)

        headers = {
            "Digest": digest,
            "Location": str(link.href),
        }

        return web.Response(
            status=200,
            headers=headers,
            content_type="application/json",
            text=res.model_dump_json(),
        )

    async def delete_store(self, request: web.Request) -> web.Response:
        """
        summary: Delete stored resource
        description: |
            Delete stored resource
        parameters:
            - in: path
              name: Name
              schema:
                type: string
              required: true
              description: Object path
            - in: query
              name: service
              schema:
                type: string
              required: true
              description: service name
            - in: query
              name: version_id
              schema:
                type: str
              required: false
              description: The version id of the resource to delete
        tags:
          - storage
        responses:
            "200":
                description: The resource has been deleted
        """
        service = self.get_service(request)
        identity = self.get_identity(request)

        name = request.match_info["Name"]

        version_id = request.query.get("version_id")

        creds = await self.store_creds()

        try:
            await store.delete_store(
                creds,
                name,
                service=service,
                identity=identity,
                version_id=version_id,
            )
        except store.StoreError as err:
            return handle_store_error(err, request)

        return web.Response(
            status=200,
            content_type="application/json",
            text=DeleteResponse(
                resource=name,
                service=service,
                role=identity,
            ).model_dump_json(),
        )

    #
    # Overridables
    #
    def read_store(
        self,
        client: store.StoreClient,
        *,
        service: str,
        identity: str,
        decode: bool,
        part_size: Optional[int] = None,
    ) -> ContextManager[store.StreamReader]:
        if decode:
            logger.error("Attempt to reach an encoded resource")
            ErrorResponse.raises(web.HTTPForbidden, "Forbidden resource")

        return store.get_store(
            client,
            service=service,
            identity=identity,
            part_size=part_size,
        )

    def write_store(
        self,
        client: store.StoreClient,
        *,
        service: str,
        identity: str,
        encode: bool,
    ) -> ContextManager[store.StreamWriter]:
        return store.put_store(
            client,
            service=service,
            identity=identity,
        )

    async def store_encrypt(
        self,
        obj: store.Object,
        stream: AsyncIterator[bytes],
        metadata: dict[str, str],
    ) -> tuple[store.Object, AsyncIterator[bytes]]:
        # Implement as a no-op
        return obj, stream

    async def store_creds(self) -> store.StoreCreds:
        if not self._store:
            ErrorResponse.raises(web.HTTPConflict, "Store not configured on server")

        conf = self._store
        return store.StoreCreds(
            endpoint=conf.endpoint,
            access_key=conf.access_key.get_secret_value(),
            secret_key=conf.secret_key.get_secret_value(),
            secure=conf.enable_tls,
            cert_check=conf.check_certificat,
            region=conf.region,
        )
