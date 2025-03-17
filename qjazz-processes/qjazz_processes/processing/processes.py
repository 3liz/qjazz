from functools import cached_property
from typing import (
    Any,
    Iterator,
    Mapping,
    Optional,
    Self,
    Sequence,
    TypeAlias,
)

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingFeedback,
    QgsProject,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.qgis import QgisPluginService
from qjazz_processes.schemas import (
    InputValueError,
    JobExecute,
    JobResults,
    LinkHttp,
    MetadataValue,
    ProcessDescription,
    ProcessSummary,
)

from . import runalg
from .context import ProcessingContext
from .inputs import InputParameter, InputParameterDef
from .outputs import OutputParameter, OutputParameterDef

ProcessingAlgorithmFlag: TypeAlias  # type: ignore [valid-type]
ProcessingAlgorithmFlags: TypeAlias  # type: ignore [valid-type]

if Qgis.QGIS_VERSION_INT >= 33600:
    # In qgis 3.36+ ProcessingAlgorithmFlags is a real python enum
    ProcessingAlgorithmFlag = Qgis.ProcessingAlgorithmFlag
    ProcessingAlgorithmFlags = Qgis.ProcessingAlgorithmFlags
else:
    from enum import Enum

    ProcessingAlgorithmFlags = QgsProcessingAlgorithm.Flags

    # NOTE: define only tested flags
    class _ProcessingAlgorithmFlag(Enum):
        HideFromToolbox = QgsProcessingAlgorithm.FlagHideFromToolbox
        CanCancel = QgsProcessingAlgorithm.FlagCanCancel
        KnownIssues = QgsProcessingAlgorithm.FlagKnownIssues
        NotAvailableInStandaloneTool = QgsProcessingAlgorithm.FlagNotAvailableInStandaloneTool
        RequiresProject = QgsProcessingAlgorithm.FlagRequiresProject
        Deprecated = QgsProcessingAlgorithm.FlagDeprecated

        def __or__(self, other: object) -> ProcessingAlgorithmFlags:
            if isinstance(other, _ProcessingAlgorithmFlag):
                other = other.value
            return self.value | other

        def __and__(self, other: object) -> ProcessingAlgorithmFlags:
            if isinstance(other, _ProcessingAlgorithmFlag):
                other = other.value
            return self.value & other

    ProcessingAlgorithmFlag = _ProcessingAlgorithmFlag


class ProcessAlgorithm:
    @classmethod
    def algorithms(
        cls,
        include_deprecated: bool = False,
        providers: Sequence[str] = (),
    ) -> Iterator[Self]:
        """Iterate over all published algorithms"""
        for provider in QgisPluginService.get_service().providers:
            if providers and provider.id() not in providers:
                continue
            for alg in provider.algorithms():
                if not cls.hidden(alg) and (include_deprecated or not cls._deprecated(alg)):
                    yield cls(alg)

    @classmethod
    def find_algorithm(cls, ident: str) -> Optional[Self]:
        """Retrieve algorithm by {provider}:{id} string"""
        alg = QgsApplication.processingRegistry().algorithmById(ident)
        return alg and cls(alg)

    # Methods

    def __init__(self, alg: QgsProcessingAlgorithm):
        self._alg = alg

    @classmethod
    def _check_flags(cls, alg: QgsProcessingAlgorithm, flags: ProcessingAlgorithmFlags) -> bool:
        return bool(flags & alg.flags())

    @property
    def ident(self) -> str:
        return self._alg.id()

    @classmethod
    def hidden(cls, alg: QgsProcessingAlgorithm) -> bool:
        return cls._check_flags(
            alg,
            ProcessingAlgorithmFlag.HideFromToolbox | ProcessingAlgorithmFlag.NotAvailableInStandaloneTool,
        )

    @classmethod
    def _deprecated(cls, alg: QgsProcessingAlgorithm) -> bool:
        return cls._check_flags(alg, ProcessingAlgorithmFlag.Deprecated)

    @property
    def require_project(self) -> bool:
        return self._check_flags(self._alg, ProcessingAlgorithmFlag.RequiresProject)

    @property
    def known_issues(self) -> bool:
        return self._check_flags(self._alg, ProcessingAlgorithmFlag.KnownIssues)

    @property
    def deprecated(self) -> bool:
        return self._deprecated(self._alg)

    @cached_property
    def _description(self) -> ProcessDescription:
        alg = self._alg

        description = ProcessDescription(
            id_=alg.id(),  # type: ignore [call-arg]
            title=alg.displayName(),
            description=alg.shortDescription(),
            version="",
        )

        # Update help link uri
        help_uri = alg.helpUrl()
        if help_uri:
            description.links.append(
                LinkHttp(
                    href=help_uri,
                    rel="about",
                    title="Process documentation",
                    mime_type="text/html",
                ),
            )

        # Update metadata
        description.metadata = [
            MetadataValue(role="QgisVersion", title="Qgis version", value=Qgis.version()),
            MetadataValue(role="QgisVersionInt", title="Qgis version int", value=Qgis.versionInt()),
            MetadataValue(role="Deprecated", title="Deprecated", value=self.deprecated),
            MetadataValue(role="KnownIssues", title="Known issues", value=self.known_issues),
            MetadataValue(role="RequiresProject", title="Requires project", value=self.require_project),
        ]

        return description

    def summary(self) -> ProcessSummary:
        return self._description

    def inputs(
        self,
        project: Optional[QgsProject] = None,
        *,
        validation_only: bool = False,
    ) -> Iterator[InputParameterDef]:
        for param in self._alg.parameterDefinitions():
            Input = InputParameter.get(param)
            if not Input.hidden(param, project):
                yield Input(param, project, validation_only=validation_only)

    def outputs(self) -> Iterator[OutputParameterDef]:
        for outp in self._alg.outputDefinitions():
            Output = OutputParameter.get(outp)
            if not Output.hidden(outp):
                yield Output(outp, self._alg)

    def description(self, project: Optional[QgsProject] = None) -> ProcessDescription:
        """Return a process description including inputs and outputs description"""
        description = self._description.model_copy(
            update=dict(
                description=self._alg.shortHelpString() or self._alg.shortDescription(),
                inputs={inp.name: inp.description() for inp in self.inputs(project)},
                outputs={out.name: out.description() for out in self.outputs()},
            ),
        )

        return description

    def validate_execute_parameters(
        self,
        request: JobExecute,
        feedback: QgsProcessingFeedback,
        context: ProcessingContext,
    ) -> tuple[
        Mapping[str, Any],
        Mapping[str, InputParameterDef],
        Sequence[OutputParameterDef],
    ]:
        """Validate parameters"""
        project = context.project()

        if self.require_project and not project:
            raise InputValueError("Algorithm {self.ident} require project")

        inputs = {i.name: i for i in self.inputs(project, validation_only=True)}

        # Handle outputs formats
        outputs = tuple(self.outputs())
        for o in outputs:
            out = request.outputs.get(o.name)
            if out:
                inputdef = o.input_definition
                o.validate_output(out, inputdef and inputs.get(inputdef.name()))

        # Convert inputs to parameters
        parameters = InputParameter.parameters(inputs.values(), request.inputs, context)

        return (parameters, inputs, outputs)

    def execute(
        self,
        request: JobExecute,
        feedback: QgsProcessingFeedback,
        context: ProcessingContext,
    ) -> JobResults:
        """Execute request"""
        # Ensure that workdir exists
        assert_precondition(
            context.workdir.is_dir(),
            f"Context workdir is not a directory: '{context.workdir}'",
        )

        # Create a destination project
        # Note: Destination project must be created *before*
        # evaluating parameters.
        if not context.destination_project:
            context.destination_project = context.create_project(self.ident)

        parameters, _, outputs = self.validate_execute_parameters(request, feedback, context)

        logger.trace("%s: %s", self.ident, parameters)

        # Run algorithm
        results = runalg.execute(self._alg, parameters, feedback, context)

        for o in outputs:
            if o.name not in results:
                raise runalg.RunProcessException(
                    f"Incomplete output for algorithm {self.ident}: {o.name}",
                )

        # Handle results
        output_values = {o.name: o.output(results[o.name], context) for o in outputs}

        # Process layer outputs
        runalg.process_layer_outputs(
            self._alg,
            context,
            feedback,
            context.workdir,
            context.destination_project,
        )

        return output_values
