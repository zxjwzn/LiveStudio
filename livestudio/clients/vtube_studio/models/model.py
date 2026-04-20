"""与模型相关的 VTube Studio 请求/响应模型。"""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import AvailableModel, ModelPosition


class CurrentModelRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取当前已加载模型。"""

    message_type: str = Field(default="CurrentModelRequest", alias="messageType", description="请求当前模型详细信息。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class CurrentModelResponseData(VTSEmptyData):
    """当前模型详细信息。"""

    model_loaded: bool = Field(alias="modelLoaded", description="是否已加载模型。")
    model_name: str = Field(alias="modelName", description="模型显示名称。")
    model_id: str = Field(alias="modelID", description="模型唯一标识。")
    vts_model_name: str = Field(alias="vtsModelName", description="VTS 模型文件名。")
    vts_model_icon_name: str = Field(alias="vtsModelIconName", description="模型图标文件名。")
    live2d_model_name: str = Field(alias="live2DModelName", description="Live2D 模型 JSON 文件名。")
    model_load_time: int = Field(alias="modelLoadTime", description="本次模型加载耗时，毫秒。")
    time_since_model_loaded: int = Field(alias="timeSinceModelLoaded", description="距离模型加载完成的毫秒数。")
    number_of_live2d_parameters: int = Field(alias="numberOfLive2DParameters", description="Live2D 参数数量。")
    number_of_live2d_artmeshes: int = Field(alias="numberOfLive2DArtmeshes", description="ArtMesh 数量。")
    has_physics_file: bool = Field(alias="hasPhysicsFile", description="是否存在物理文件。")
    number_of_textures: int = Field(alias="numberOfTextures", description="纹理数量。")
    texture_resolution: int = Field(alias="textureResolution", description="纹理分辨率。")
    model_position: ModelPosition = Field(alias="modelPosition", description="模型位置、旋转、大小。")


class CurrentModelResponse(VTSResponseEnvelope[CurrentModelResponseData]):
    """当前模型响应信封。"""


class AvailableModelsRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取可用模型列表。"""

    message_type: str = Field(default="AvailableModelsRequest", alias="messageType", description="请求本地全部可用模型。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class AvailableModelsResponseData(VTSEmptyData):
    """可用模型列表。"""

    number_of_models: int = Field(alias="numberOfModels", description="模型总数。")
    available_models: list[AvailableModel] = Field(alias="availableModels", description="模型列表。")


class AvailableModelsResponse(VTSResponseEnvelope[AvailableModelsResponseData]):
    """可用模型列表响应。"""


class ModelLoadRequestData(VTSEmptyData):
    """加载或卸载模型。"""

    model_id: str = Field(alias="modelID", description="目标模型 ID；空字符串表示卸载当前模型。")


class ModelLoadRequest(VTSRequestEnvelope[ModelLoadRequestData]):
    """加载指定模型。"""

    message_type: str = Field(default="ModelLoadRequest", alias="messageType", description="请求加载指定模型。")


class ModelLoadResponseData(VTSEmptyData):
    """模型加载结果。"""

    model_id: str = Field(alias="modelID", description="实际被加载的模型 ID。")


class ModelLoadResponse(VTSResponseEnvelope[ModelLoadResponseData]):
    """模型加载响应。"""


class MoveModelRequestData(VTSEmptyData):
    """移动当前模型。"""

    time_in_seconds: float = Field(alias="timeInSeconds", ge=0, le=2, description="移动过渡时长，秒。0 表示瞬移。")
    values_are_relative_to_model: bool = Field(alias="valuesAreRelativeToModel", description="坐标、旋转、尺寸是否相对当前模型状态。")
    position_x: float | None = Field(default=None, alias="positionX", ge=-1000, le=1000, description="可选目标 X 坐标。")
    position_y: float | None = Field(default=None, alias="positionY", ge=-1000, le=1000, description="可选目标 Y 坐标。")
    rotation: float | None = Field(default=None, ge=-360, le=360, description="可选目标旋转角度。")
    size: float | None = Field(default=None, ge=-100, le=100, description="可选目标尺寸。")


class MoveModelRequest(VTSRequestEnvelope[MoveModelRequestData]):
    """移动当前模型请求。"""

    message_type: str = Field(default="MoveModelRequest", alias="messageType", description="请求移动当前已加载模型。")


class MoveModelResponse(VTSResponseEnvelope[VTSEmptyData]):
    """移动模型响应。"""
