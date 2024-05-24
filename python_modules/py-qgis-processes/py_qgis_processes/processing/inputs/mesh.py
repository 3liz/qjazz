
from datetime import datetime

from pydantic import BaseModel, Field, JsonValue, TypeAdapter
from typing_extensions import (
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Union,
)

from qgis.core import (
    QgsMeshDatasetGroupMetadata,
    QgsProcessingUtils,
    QgsProject,
)
from qgis.PyQt.QtCore import QDateTime

from .base import (
    InputParameter,
    Metadata,
    MetadataValue,
    ParameterDefinition,
    ProcessingContext,
)
from .layers import ParameterMapLayer

#
# QgsProcessingParameterMeshLayer
#


class ParameterMeshLayer(ParameterMapLayer):
    @classmethod
    def compatible_layers(cls, param: ParameterDefinition, project: QgsProject) -> Iterable[str]:
        return QgsProcessingUtils.compatibleMeshLayers(project)


#
# QgsProcessingParameterMeshDatasetGroups
#

class ParameterMeshDatasetGroups(InputParameter):
    _ParameterType = Set[
        Literal[        # type: ignore [valid-type]
            QgsMeshDatasetGroupMetadata.DataOnFaces,
            QgsMeshDatasetGroupMetadata.DataOnVertices,
            QgsMeshDatasetGroupMetadata.DataOnVolumes,
            QgsMeshDatasetGroupMetadata.DataOnEdges,
        ],
    ]

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        mesh_layer_param = param.meshLayerParameterName()
        if mesh_layer_param:
            md.append(
                MetadataValue(
                    role="meshLayerParameterName",
                    value=mesh_layer_param,
                ),
            )

        return md


#
# QgsProcessingParameterMeshDatasetTime
#

class DefinedDatetime(BaseModel):
    type_: Literal['defined-date-time'] = Field(alias='type')
    value: datetime


class DatasetTimeStep(BaseModel):
    type_: Literal['dataset-time-step'] = Field(alias='type')
    value: Sequence[int] = Field(max_length=2, min_length=2)


class StaticDateTime(BaseModel):
    type_: Literal['static'] = Field(alias='type')


class CurrentContextTime(BaseModel):
    type_: Literal['current-context-time'] = Field(alias='type')


def _to_json_schema(t):
    s = TypeAdapter(t).json_schema(by_alias=True)
    del s['title']
    for p in s['properties'].values():
        del p['title']
    return s


class ParameterMeshDatasetTime(InputParameter):
    _ParameterType = Union[
        DefinedDatetime,
        DatasetTimeStep,
        StaticDateTime,
        CurrentContextTime,
    ]

    def json_schema(self) -> Dict[str, JsonValue]:
        return {
            'oneOf': [
                _to_json_schema(DefinedDatetime),
                _to_json_schema(DatasetTimeStep),
                _to_json_schema(StaticDateTime),
                _to_json_schema(CurrentContextTime),
            ],
        }

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        mesh_layer_param = param.meshLayerParameterName()
        if mesh_layer_param:
            md.append(
                MetadataValue(
                    role="meshLayerParameterName",
                    value=mesh_layer_param,
                ),
            )
        group_param = param.datasetGroupParameterName()
        if group_param:
            md.append(
                MetadataValue(
                    role="datasetGroupParameterName",
                    value=group_param,
                ),
            )

        return md

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QDateTime | Dict:

        _inp = self.validate(inp)

        if isinstance(_inp, DefinedDatetime):
            return QDateTime(_inp.value)
        else:
            return _inp.model_dump(mode='json', by_alias=True)
