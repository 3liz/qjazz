from typing import (
    Annotated,
    Callable,
    Optional,
    Sequence,
)

import celery.exceptions

from aiohttp import web
from pydantic import Field, PositiveInt, TypeAdapter, ValidationError
from qjazz_core import logger

from ...schemas import get_annotation
from ..headers import QJAZZ_IDENTITY_HEADER
from .protos import (
    JOB_ID_HEADER,
    JOB_REALM_HEADER,
    ErrorResponse,
    HandlerProto,
    InputValueError,
    JobExecute,
    JobResultsAdapter,
    JobStatus,
    JsonDict,
    Link,
    ProcessNotFound,
    ProcessSummary,
    ProjectRequired,
    RunProcessException,
    ServiceNotAvailable,
    href,
    make_link,
    public_url,
    swagger,
    validate_param,
)


@swagger.model
class ProcessList(swagger.JsonModel):
    processes: Sequence[ProcessSummary]
    links: Sequence[Link]


TagParam: TypeAdapter[Optional[str]] = TypeAdapter(Annotated[Optional[str], Field(max_length=36)])


class Processes(HandlerProto):
    async def list_processes(self, request: web.Request) -> web.Response:
        """
        summary: Get available processes
        description: |
            Returns the list of available processes
        parameters:
            - in: query
              name: service
              schema:
                type: string
              required: false
              description: |
                The service requested.
                If not set, the default behavior is to return
                the first service in the configured service list.
        tags:
            - processes
        responses:
            "200":
                description: >
                    Returns the list of process summaries
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ProcessList'
        """
        # Get service processes from cache
        service = self.get_service(request)
        try:
            processes = await self._executor.processes(service, timeout=self._timeout)
        except celery.exceptions.TimeoutError:
            ErrorResponse.raises(web.HTTPServiceUnavailable, "Service is not available")

        def _process_filter(td: ProcessSummary) -> Optional[ProcessSummary]:
            if self._accesspolicy.execute_permission(request, service, td.id_):
                td.links = [
                    make_link(
                        request,
                        path=self.format_path(request, f"/processes/{td.id_}", service),
                        rel="http://www.opengis.net/def/rel/ogc/1.0/processes",
                        title="Process description",
                    ),
                    *td.links,
                ]
                return td
            return None

        return web.Response(
            content_type="application/json",
            text=ProcessList(
                processes=list(
                    filter(None, (_process_filter(td) for td in processes)),
                ),
                links=[
                    make_link(
                        request,
                        path=self.format_path(request, "/processes/", service),
                        rel="self",
                        title="Processes list",
                    ),
                ],
            ).model_dump_json(),
        )

    async def describe_process(self, request: web.Request) -> web.Response:
        """
        summary: Get process description
        description: |
            Return the process description for
            the given service and  process identifier
        parameters:
            - in: path
              name: Ident
              schema:
                type: string
              required: true
              description: process identifier
        tags:
          - processes
        responses:
            "200":
                description: >
                    Returns the process description
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ProcessDescription'
        """
        service = self.get_service(request)
        project = self.get_project(request)

        process_id = request.match_info["Ident"]

        self.check_process_permission(request, service, process_id, project)

        try:
            td = await self._executor.describe(
                service,
                process_id,
                project=project,
                timeout=self._timeout,
            )
        except celery.exceptions.TimeoutError:
            ErrorResponse.raises(web.HTTPServiceUnavailable, f"Service {service} is not available")
        except ServiceNotAvailable:
            ErrorResponse.raises(
                web.HTTPForbidden,
                "Service not available",
                details={"service": service},
            )

        if not td:
            ErrorResponse.raises(web.HTTPForbidden, f"{process_id} not available")

        return web.Response(
            content_type="application/json",
            text=td.model_copy(
                update={
                    "links": [
                        make_link(
                            request,
                            path=self.format_path(
                                request,
                                f"/processes/{process_id}",
                                service,
                                project,
                            ),
                            rel="self",
                            title="Process description",
                        ),
                        make_link(
                            request,
                            path=self.format_path(
                                request,
                                f"/processes/{process_id}/execution",
                                service,
                                project,
                            ),
                            rel="http://www.opengis.net/def/rel/ogc/1.0/processes]",
                            title="Execute process",
                        ),
                        *td.links,
                    ],
                },
            ).model_dump_json(),
        )

    async def execute_process(self, request: web.Request) -> web.Response:
        """
        summary: Execute process
        description: |
            Execute the process and returns the job status
        parameters:
            - in: path
              name: Ident
              schema:
                type: string
              required: true
              description: Process identifier
            - in: query
              name: tag
              schema:
                type: string
                maxLength: 36
              required: false
              description: job tag
        tags:
          - processes
        requestBody:
            required: true
            description: |-
                An execution request specifying any inputs for the process to execute,
                and optionally to select specific outputs.
            content:
                application/json:
                    schema:
                        $ref: '#/definitions/JobExecute'
        responses:
            "200":
                description: >
                    Process executed succesfully.
                    Only returned in case of synchronous execution.
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobResults'
            "202":
                description: >
                    Process accepted.
                    Returned in case of asynchronous execution.
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobStatus'
        """
        tag = validate_param(TagParam, request, "tag", None)

        service = self.get_service(request)
        project = self.get_project(request)

        process_id = request.match_info["Ident"]

        self.check_process_permission(request, service, process_id, project)

        try:
            execute_request = JobExecute.model_validate_json(await request.text())
        except ValidationError as err:
            logger.error("Invalid request: %s", err)
            raise web.HTTPBadRequest(
                content_type="application/json",
                text=err.json(include_context=False, include_url=False),
            )

        # Get execute preferences
        prefer = ExecutePrefs(request)

        # Set job realm
        realm = self._jobrealm.get_job_realm(request)

        # Allow setting priority only if admin
        if prefer.priority is not None and self._jobrealm.is_admin(realm):
            priority = prefer.priority
        else:
            priority = 0

        # Check process
        process = await self._executor.get_process_summary(service, process_id)
        if not process:
            return ErrorResponse.response(
                404,
                "Process not found",
                details={"processId": process_id},
            )

        execute_sync = prefer.execute_sync() and "sync-execute" in process.job_control_options
        if execute_sync:
            logger.debug("Running synchronous execution for %s (%s)", process_id, service)

        context = await self.create_run_context(service, process, request)

        result = self._executor.execute(
            service,
            process_id,
            request=execute_request,
            project=project,
            context=context,
            realm=realm,
            # Set the pending timeout to the wait preference
            pending_timeout=prefer.wait,
            tag=tag,
            priority=priority,
            # Set execution delay only if asynchronous execution
            countdown=prefer.delay if not execute_sync else None,
        )

        if execute_sync:
            try:
                job_result = await result.get(prefer.wait or self._timeout)
                headers = {JOB_ID_HEADER: result.job_id}
                if realm:
                    headers[JOB_REALM_HEADER] = realm
                return web.Response(
                    status=200,
                    headers=headers,
                    content_type="application/json",
                    body=JobResultsAdapter.dump_json(job_result, by_alias=True, exclude_none=True),
                )
            except celery.exceptions.TimeoutError:
                # Check for allowed async execution
                # If wait is set then fallback to asynchronous response
                if not prefer.execute_async:
                    logger.error("Synchronous request timeout")
                    # Dismiss task
                    job_status = await self._executor.dismiss(result.job_id)
                    raise web.HTTPGatewayTimeout(
                        content_type="application/json",
                        text=job_status.model_dump_json() if job_status else "{}",
                    )
                logger.warning(
                    "Synchronous request timeout: falling back to async response.",
                )
            #
            # Handle parameter error as
            # bad request (400)
            #
            except InputValueError as err:
                logger.error("Input value error %s", err)
                raise web.HTTPBadRequest(
                    content_type="application/json",
                    text=str(err),
                )
            #
            # Processing exception
            #
            except RunProcessException as err:
                logger.error("Processing exception [job: %s]: %s", result.job_id, err)
                return ErrorResponse.response(
                    status=500,
                    message="Internal processing error",
                    details={"jobId": result.job_id},
                )
            #
            # Process not found
            #
            except ProcessNotFound as err:
                logger.error("Process exception [job: %s]: %s", result.job_id, err)
                ErrorResponse.raises(
                    web.HTTPNotFound,
                    f"{process_id} not found",
                    details={"jobId": result.job_id},
                )
            #
            # Project is required
            #
            except ProjectRequired as err:
                logger.error("Process exception [job: %s]: %s", result.job_id, err)
                ErrorResponse.raises(
                    web.HTTPBadRequest,
                    f"{process_id} require a project",
                    details={"jobId": result.job_id},
                )

        job_status = await result.status()

        location = self.format_path(request, f"/jobs/{job_status.job_id}")

        job_status.links = [
            make_link(
                request,
                path=location,
                rel="http://www.opengis.net/def/rel/iana/1.0/status",
                title="job status",
            ),
            make_link(
                request,
                path=self.format_path(
                    request,
                    f"/processes/{job_status.process_id}/execution",
                    service,
                    project,
                ),
                rel="self",
                title="job execution",
            ),
        ]

        if job_status.status == JobStatus.SUCCESS:
            location = self.format_path(request, f"/jobs/{job_status.job_id}/results")
            job_status.links.append(
                make_link(
                    request,
                    path=location,
                    rel="http://www.opengis.net/def/rel/ogc/1.0/results",
                ),
            )

        headers = {"Location": href(request, location)}

        if realm:
            headers[JOB_REALM_HEADER] = realm

        # Return 'Accepted' response
        return web.Response(
            status=202,
            headers=headers,
            content_type="application/json",
            text=job_status.model_dump_json(),
        )

    def check_process_permission(
        self,
        request: web.Request,
        service: str,
        process_id: str,
        project: Optional[str],
    ):
        if not self._accesspolicy.execute_permission(request, service, process_id, project):
            ErrorResponse.raises(
                web.HTTPForbidden,
                f"Process {process_id} not available",
            )

    def get_default_run_context(
        self,
        service: str,
        process: ProcessSummary,
        request: web.Request,
    ) -> JsonDict:
        return {"public_url": public_url(request, "")}

    # Overridable
    async def create_run_context(
        self,
        service: str,
        process: ProcessSummary,
        request: web.Request,
    ) -> JsonDict:
        context = self.get_default_run_context(service, process, request)

        # Do the service process require a store ?
        if get_annotation("RequireStore", process):
            from ..context import update_store_context

            creds = await self.store_creds()

            await update_store_context(
                context,
                process,
                service,
                self.get_identity(request),
                creds,
                # Getting creds ensure that store is configured
                ttl=self._store.acces_ttl,  # type: ignore [union-attr]
            )

        return context

    def get_identity(self, request: web.Request) -> str:
        identity = request.headers.get(QJAZZ_IDENTITY_HEADER)
        if not identity:
            ErrorResponse.raises(web.HTTPUnauthorized, "Identity required")

        return identity


#
# Handle HTTP Prefer header
#


class ExecutePrefs:
    execute_async: bool = False
    wait: Optional[int] = None
    priority: Optional[int] = None
    delay: Optional[int] = None

    as_seconds: Callable[[str], int] = TypeAdapter(PositiveInt).validate_python
    as_priority: Callable[[str], int] = TypeAdapter(Annotated[int, Field(ge=0, lt=10)]).validate_python

    def execute_sync(self) -> bool:
        return self.delay is None and (not self.execute_async or self.wait is not None)

    def __init__(self, request: web.Request):
        """Get execution preferences from 'Prefer' header

        See https://webconcepts.info/concepts/http-preference/
        See https://docs.ogc.org/is/18-062r2/18-062r2.html#toc32
        """
        for prefer in request.headers.getall("Prefer", ()):
            for pref in (p.strip().lower() for p in prefer.split(",")):
                try:
                    if pref == "respond-async":
                        self.execute_async = True
                    elif pref.startswith("wait="):
                        self.wait = self.as_seconds(pref[5:])
                    elif pref.startswith("priority="):
                        self.priority = self.as_priority(pref[9:])
                    elif pref.startswith("delay="):
                        self.delay = self.as_seconds(pref[6:])
                except ValidationError:
                    logger.error("Invalid value in Prefer header: %s", pref)
