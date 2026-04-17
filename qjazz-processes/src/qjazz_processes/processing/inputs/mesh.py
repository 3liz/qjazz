from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Iterable,
    Literal,
    Optional,
    Sequence,
    Union,
    cast,
)

from pydantic import BaseModel, Field, JsonValue, TypeAdapter

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

if TYPE_CHECKING:
    from qgis.core import (
        QgsMeshLayer,
        QgsProcessingParameterMeshDatasetGroups,
        QgsProcessingParameterMeshDatasetTime,
    )

#
# QgsProcessingParameterMeshLayer
#


class ParameterMeshLayer(ParameterMapLayer):
    @classmethod
    def compatible_layers(
        cls,
        param: ParameterDefinition,
        project: QgsProject,
    ) -> Iterable["QgsMeshLayer"]:
        return QgsProcessingUtils.compatibleMeshLayers(project)


#
# QgsProcessingParameterMeshDatasetGroups
#


class ParameterMeshDatasetGroups(InputParameter):
    _ParameterType = set[
        Literal[  # type: ignore [valid-type]
            QgsMeshDatasetGroupMetadata.DataType.DataOnFaces,
            QgsMeshDatasetGroupMetadata.DataType.DataOnVertices,
            QgsMeshDatasetGroupMetadata.DataType.DataOnVolumes,
            QgsMeshDatasetGroupMetadata.DataType.DataOnEdges,
        ],
    ]

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> list[Metadata]:
        md = super(ParameterMeshDatasetGroups, cls).metadata(param)

        tparam = cast("QgsProcessingParameterMeshDatasetGroups", param)
        mesh_layer_param = tparam.meshLayerParameterName()
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
    type_: Literal["defined-date-time"] = Field(alias="type")
    value: datetime


class DatasetTimeStep(BaseModel):
    type_: Literal["dataset-time-step"] = Field(alias="type")
    value: Sequence[int] = Field(max_length=2, min_length=2)


class StaticDateTime(BaseModel):
    type_: Literal["static"] = Field(alias="type")


class CurrentContextTime(BaseModel):
    type_: Literal["current-context-time"] = Field(alias="type")


def _to_json_schema(t):
    s = TypeAdapter(t).json_schema(by_alias=True)
    del s["title"]
    for p in s["properties"].values():
        del p["title"]
    return s


class ParameterMeshDatasetTime(InputParameter):
    _ParameterType = Union[
        DefinedDatetime,
        DatasetTimeStep,
        StaticDateTime,
        CurrentContextTime,
    ]

    def json_schema(self) -> dict[str, JsonValue]:
        return {
            "oneOf": [
                _to_json_schema(DefinedDatetime),
                _to_json_schema(DatasetTimeStep),
                _to_json_schema(StaticDateTime),
                _to_json_schema(CurrentContextTime),
            ],
        }

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> list[Metadata]:
        md = super(ParameterMeshDatasetTime, cls).metadata(param)

        tparam = cast("QgsProcessingParameterMeshDatasetTime", param)
        mesh_layer_param = tparam.meshLayerParameterName()
        if mesh_layer_param:
            md.append(
                MetadataValue(
                    role="meshLayerParameterName",
                    value=mesh_layer_param,
                ),
            )
        group_param = tparam.datasetGroupParameterName()
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
    ) -> QDateTime | dict:
        _inp = self.validate(inp)

        if isinstance(_inp, DefinedDatetime):
            return QDateTime(_inp.value)
        return _inp.model_dump(mode="json", by_alias=True)
