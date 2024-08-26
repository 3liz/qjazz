
import re

import celery.exceptions

from aiohttp import web
from pydantic import ValidationError
from typing_extensions import (
    Optional,
    Sequence,
)

from py_qgis_contrib.core import logger

from .protos import (
    JOB_REALM_HEADER,
    ErrorResponse,
    HandlerProto,
    InputValueError,
    JobExecute,
    JobResultsAdapter,
    JobStatus,
    Link,
    ProcessSummary,
    RunProcessingException,
    get_job_realm,
    href,
    make_link,
    public_url,
    swagger,
)


@swagger.model
class ProcessList(swagger.JsonModel):
    processes: Sequence[ProcessSummary]
    links: Sequence[Link]


class Processes(HandlerProto):

    async def list_processes(self, request: web.Request) -> web.Response:
        """
        summary: Get available processes
        description: |
            Returns the list of available for the
            given ServiceId
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
        service = self.get_service(request, raise_error=False)
        processes = self._cache.get(service)
        if processes is None:
            ErrorResponse.raises(web.HTTPServiceUnavailable, "Service is not available")

        def _process_filter(td: ProcessSummary) -> bool:
            return self._accesspolicy.execute_permission(request, service, td.id_)

        return web.Response(
            content_type="application/json",
            text=ProcessList(
                processes=[
                    td.model_copy(
                        update=dict(
                            links=[
                                make_link(
                                    request,
                                    path=self.format_path(request, f"/processes/{td.id_}", service),
                                    rel="http://www.opengis.net/def/rel/ogc/1.0/processes",
                                    title="Process description",
                                ),
                                *td.links,
                            ],
                        ),
                    ) for td in processes if _process_filter(td)
                ],
                links=[
                    make_link(
                        request,
                        path=self.format_path(request, "/jobs/", service),
                        rel="self",
                        title="Job list",
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

        process_id = request.match_info['Ident']

        if not self._cache.exists(service, process_id):
            ErrorResponse.raises(web.HTTPForbidden, f"{process_id} is not available")

        self.check_process_permission(request, service, process_id, project)

        try:
            td = await self._executor.describe(
                service,
                process_id,
                project=project,
                timeout=self._timeout,
            )
        except TimeoutError:
            ErrorResponse.raises(web.HTTPGatewayTimeout, "Worker busy")

        if not td:
            ErrorResponse.raises(web.HTTPForbidden, f"{process_id} not available")

        return web.Response(
            content_type="application/json",
            text=td.model_copy(
                update=dict(
                    links=[
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
                ),
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
              description: Process  identifier
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
            "201":
                description: >
                    Process accepted
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobStatus'
        """
        service = self.get_service(request)
        project = self.get_project(request)

        process_id = request.match_info['Ident']

        if not self._cache.exists(service, process_id):
            ErrorResponse.raises(web.HTTPForbidden, f"{process_id} is not available")

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
        realm = get_job_realm(request)

        result = await self._executor.execute(
            service,
            process_id,
            request=execute_request,
            project=project,
            context=dict(
                public_url=public_url(request, ""),
            ),
            realm=realm,
            # Set the pending timeout to the wait preference
            pending_timeout=prefer.wait,
        )

        if not prefer.execute_async or (prefer.execute_async and prefer.wait is not None):
            try:
                job_result = await result.get(prefer.wait or self._timeout)
                return web.Response(
                    status=200,
                    headers={JOB_REALM_HEADER: realm} if realm else None,
                    content_type="application/json",
                    body=JobResultsAdapter.dump_json(job_result, by_alias=True, exclude_none=True),
                )
            except celery.exceptions.TimeoutError:
                # If wait is set then fallback to asynchronous response
                if not prefer.execute_async:
                    logger.error("Synchronous request timeout")
                    # Dismiss task
                    job_status = await self._executor.dismiss(result.job_id)
                    raise web.HTTPGatewayTimeout(
                        content_type="application/json",
                        text=job_status.model_dump_json() if job_status else "{}",
                    )
                else:
                    logger.warning(
                        "Synchronous request timeout: "
                        "falling back to async response.",
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
            except RunProcessingException as err:
                logger.error("Processing exception [job: %s]: %s", result.job_id, err)
                raise web.HTTPInternalServerError(
                    content_type="application/json",
                    text=f'{ "message": "Internal processing error" }',
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
            make_link(
                request,
                path=self.format_path(request, f"/processes/{job_status.job_id}/results"),
                rel="http://www.opengis.net/def/rel/ogc/1.0/processes",
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

        headers = {
            'Location': href(request, location),
            'Preference-Applied': 'respond-async',
        }

        if realm:
            headers[JOB_REALM_HEADER] = realm

        return web.Response(
            status=201,
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
                web.HTTPUnauthorized,
                "You are not allowed to access this process",
            )


#
# Handle HTTP Prefer header
#

WAIT_PARAM = re.compile(r',?\s*wait=(\d+)\s*')


class ExecutePrefs:

    execute_async: bool = False
    wait: Optional[int] = None

    def __init__(self, request: web.Request):
        """ Get execution preferences from 'Prefer' header

            See https://webconcepts.info/concepts/http-preference/
            See https://docs.ogc.org/is/18-062r2/18-062r2.html#toc32
        """
        for prefer in request.headers.getall('Prefer', ()):
            for pref in (p.strip().lower() for p in prefer.split(';')):
                if self.wait is None and pref.startswith('wait'):
                    m = WAIT_PARAM.fullmatch(pref)
                    if m:
                        self.wait = int(m.groups()[0])
                if pref.startswith('respond-async'):
                    self.execute_async = True
                    m = WAIT_PARAM.fullmatch(pref[13:])
                    if m:
                        self.wait = int(m.groups()[0])
