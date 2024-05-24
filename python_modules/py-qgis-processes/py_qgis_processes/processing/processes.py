
from functools import cached_property

from typing_extensions import (
    Iterator,
    Optional,
    TypeAlias,
)

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProject,
)

from py_qgis_processes_schemas import (
    LinkHttp,
    MetadataValue,
    ProcessesDescription,
    ProcessesSummary,
)

from .inputs import InputParameter, InputParameterDef
from .outputs import OutputParameter, OutputParameterDef

ProcessingAlgorithmFlag: TypeAlias   # type: ignore [valid-type]
ProcessingAlgorithmFlags: TypeAlias  # type: ignore [valid-type]

if Qgis.QGIS_VERSION_INT >= 33600:
    # In qgis 3.36+ ProcessingSourceType is a real python enum
    ProcessingAlgorithmFlag = Qgis.ProcessingAlgorithmFlag
    ProcessingAlgorithmFlags = QgsProcessingAlgorithm.ProcessingAlgorithmFlags
else:
    from enum import Enum

    # NOTE: define tested flags
    class _ProcessingAlgorithmFlag(Enum):
        HideFromToolboox = QgsProcessingAlgorithm.HideFromToolboox
        CanCancel = QgsProcessingAlgorithm.FlagCanCancel
        KnownIssues = QgsProcessingAlgorithm.FlagKnownIssues
        NotAvailableInStandaloneTool = QgsProcessingAlgorithm.FlagNotAvailableInStandaloneTool
        RequireProject = QgsProcessingAlgorithm.FlagRequireProject
        Deprecated = QgsProcessingAlgorithm.FlagDeprecated

    ProcessingAlgorithmFlag = _ProcessingAlgorithmFlag
    ProcessingAlgorithmFlags = QgsProcessingAlgorithm.Flags


class ProcessAlg:

    def __init__(self, alg: QgsProcessingAlgorithm):
        self._alg = alg

    def _check_flags(self, flags: ProcessingAlgorithmFlags) -> bool:
        return bool(self._alg.flags() & flags)

    @property
    def hidden(self) -> bool:
        return self._check_flags(
            ProcessingAlgorithmFlag.HideFromToolboox
            | ProcessingAlgorithmFlag.NotAvailableInStandaloneTool,
        )

    @property
    def require_project(self) -> bool:
        return self._check_flags(ProcessingAlgorithmFlag.RequireProject)

    @property
    def known_issues(self) -> bool:
        return self._check_flags(ProcessingAlgorithmFlag.KnownIssues)

    @property
    def deprecated(self) -> bool:
        return self._check_flags(ProcessingAlgorithmFlag.Deprecated)

    @cached_property
    def _description(self):

        alg = self._alg

        description = ProcessesDescription(
            _id=alg.id(),
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
            MetadataValue(role="Deprecated", title="Deprecated", value=self.deprecated),
            MetadataValue(role="KnownIssues", title="Known issues", value=self.known_issues),
            MetadataValue(role="RequireProject", title="Require project", value=self.require_project),
        ]

        helpstr = alg.shortHelpString()
        if helpstr:
            description.metadata.append(
                MetadataValue(role="HelpString", title="Help", value=helpstr),
            )

        return description

    def summary(self) -> ProcessesSummary:
        return self._description

    def inputs(
        self,
        project: Optional[QgsProject] = None,
        *,
        validation_only: bool = False,
    ) -> Iterator[InputParameterDef]:
        for param in self._alg.parameterDefinitions():
            if not InputParameter.is_hidden(param, project):  # type: ignore [attr-defined]
                yield InputParameter(param, project, validation_only=validation_only)

    def outputs(self) -> Iterator[OutputParameterDef]:
        for outp in self._alg.outputDefinitions():
            yield OutputParameter(outp, self._alg)

    def description(self, project: Optional[QgsProject] = None) -> ProcessesDescription:
        """ Return a process description including inputs and outputs description
        """
        description = self._description.copy()

        description.inputs = {inp.name: inp.description() for inp in self.inputs(project)}
        description.outputs = {out.name: out.description() for out in self.outputs()}

        return description
