from aiohttp import web
from pydantic import JsonValue, ValidationError
from typing_extensions import (
    List,
    Optional,
    Sequence,
    cast,
)

from .protos import (
    JOB_REALM_HEADER,
    ErrorResponse,
    HandlerProto,
    JobExecute,
    JobStatus,
    Link,
    ProcessSummary,
    ProcessDescription,
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
            ErrorResponse.raises(web.HTTPServiceUnavailable, "Service not available")

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
            return ErrorResponse.response(404, f"The process {process_id} does not exists")

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

        self.check_process_permission(request, service, process_id, project)

        try:
            execute_request = JobExecute.model_validate_json(await request.text())
        except ValidationError as err:
            ErrorResponse.raises(
                web.HTTPBadRequest,
                message="Invalid body",
                details=cast(
                    List[JsonValue],
                    err.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    ),
                ),
            )

        # Set job realm
        realm = get_job_realm(request)

        job_status = await self._executor.execute(
            service,
            process_id,
            request=execute_request,
            project=project,
            context=dict(
                public_url=public_url(request, ""),
            ),
            realm=realm,
        )

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
