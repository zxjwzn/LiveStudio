"""与参数和物理相关的请求/响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import InjectParameterValue, ParameterInfo, PhysicsGroup, PhysicsOverride


class InputParameterListRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取默认与自定义输入参数列表。"""

    message_type: str = Field(default="InputParameterListRequest", alias="messageType", description="请求当前可用的输入参数列表。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class InputParameterListResponseData(VTSEmptyData):
    """输入参数列表响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载模型。")
    model_name: str = Field(alias="modelName", description="当前模型名称。")
    model_id: str = Field(alias="modelID", description="当前模型 ID。")
    custom_parameters: list[ParameterInfo] = Field(alias="customParameters", description="全部自定义参数。")
    default_parameters: list[ParameterInfo] = Field(alias="defaultParameters", description="全部默认输入参数。")


class InputParameterListResponse(VTSResponseEnvelope[InputParameterListResponseData]):
    """输入参数列表响应信封。"""


class ParameterValueRequestData(VTSEmptyData):
    """查询单个参数值。"""

    name: str = Field(description="待查询参数名称。")


class ParameterValueRequest(VTSRequestEnvelope[ParameterValueRequestData]):
    """参数值查询请求。"""

    message_type: str = Field(default="ParameterValueRequest", alias="messageType", description="请求单个参数的当前值。")


class ParameterValueResponseData(ParameterInfo):
    """单个参数值响应。"""


class ParameterValueResponse(VTSResponseEnvelope[ParameterValueResponseData]):
    """参数值响应信封。"""


class Live2DParameterListRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取当前模型所有 Live2D 参数值。"""

    message_type: str = Field(default="Live2DParameterListRequest", alias="messageType", description="请求当前模型所有 Live2D 参数。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class Live2DParameterListResponseData(VTSEmptyData):
    """Live2D 参数列表响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载模型。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    parameters: list[ParameterInfo] = Field(description="Live2D 参数列表。")


class Live2DParameterListResponse(VTSResponseEnvelope[Live2DParameterListResponseData]):
    """Live2D 参数列表响应信封。"""


class ParameterCreationRequestData(VTSEmptyData):
    """创建自定义输入参数。"""

    parameter_name: str = Field(alias="parameterName", min_length=4, max_length=32, description="参数名称，仅允许字母数字且不能包含空格。")
    explanation: str | None = Field(default=None, max_length=255, description="可选说明文本，指导用户如何使用该参数。")
    min: float = Field(ge=-1000000, le=1000000, description="建议最小值。")
    max: float = Field(ge=-1000000, le=1000000, description="建议最大值。")
    default_value: float = Field(alias="defaultValue", ge=-1000000, le=1000000, description="默认值。")


class ParameterCreationRequest(VTSRequestEnvelope[ParameterCreationRequestData]):
    """创建自定义参数请求。"""

    message_type: str = Field(default="ParameterCreationRequest", alias="messageType", description="请求创建或覆盖同名自定义参数。")


class ParameterCreationResponseData(VTSEmptyData):
    """自定义参数创建响应。"""

    parameter_name: str = Field(alias="parameterName", description="创建成功的参数名称。")


class ParameterCreationResponse(VTSResponseEnvelope[ParameterCreationResponseData]):
    """自定义参数创建响应信封。"""


class ParameterDeletionRequestData(VTSEmptyData):
    """删除自定义参数。"""

    parameter_name: str = Field(alias="parameterName", description="待删除的自定义参数名称。")


class ParameterDeletionRequest(VTSRequestEnvelope[ParameterDeletionRequestData]):
    """删除自定义参数请求。"""

    message_type: str = Field(default="ParameterDeletionRequest", alias="messageType", description="请求删除自定义输入参数。")


class ParameterDeletionResponseData(VTSEmptyData):
    """删除自定义参数响应。"""

    parameter_name: str = Field(alias="parameterName", description="已删除的参数名称。")


class ParameterDeletionResponse(VTSResponseEnvelope[ParameterDeletionResponseData]):
    """删除自定义参数响应信封。"""


class InjectParameterDataRequestData(VTSEmptyData):
    """注入参数跟踪数据。"""

    face_found: bool | None = Field(default=None, alias="faceFound", description="可选：显式告知是否检测到人脸。")
    mode: Literal["set", "add"] = Field(default="set", description="注入模式：`set` 覆盖、`add` 累加。")
    parameter_values: list[InjectParameterValue] = Field(alias="parameterValues", min_length=1, description="待注入的参数值列表。")


class InjectParameterDataRequest(VTSRequestEnvelope[InjectParameterDataRequestData]):
    """注入参数数据请求。"""

    message_type: str = Field(default="InjectParameterDataRequest", alias="messageType", description="请求向默认或自定义参数写入数据。")


class InjectParameterDataResponse(VTSResponseEnvelope[VTSEmptyData]):
    """注入参数数据响应。"""


class GetCurrentModelPhysicsRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取当前模型物理设置。"""

    message_type: str = Field(default="GetCurrentModelPhysicsRequest", alias="messageType", description="请求当前模型的物理配置。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class GetCurrentModelPhysicsResponseData(VTSEmptyData):
    """当前模型物理配置响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载模型。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    model_has_physics: bool = Field(alias="modelHasPhysics", description="模型是否存在可用物理配置。")
    physics_switched_on: bool = Field(alias="physicsSwitchedOn", description="用户是否启用物理。")
    using_legacy_physics: bool = Field(alias="usingLegacyPhysics", description="是否启用旧版物理。")
    physics_fps_setting: int = Field(alias="physicsFPSSetting", description="物理帧率设置，-1 表示跟随应用帧率。")
    base_strength: int = Field(alias="baseStrength", description="基础物理强度。")
    base_wind: int = Field(alias="baseWind", description="基础风力。")
    api_physics_override_active: bool = Field(alias="apiPhysicsOverrideActive", description="是否有插件正在覆盖物理配置。")
    api_physics_override_plugin_name: str = Field(alias="apiPhysicsOverridePluginName", description="当前占用物理控制权的插件名称。")
    physics_groups: list[PhysicsGroup] = Field(alias="physicsGroups", description="物理分组配置列表。")


class GetCurrentModelPhysicsResponse(VTSResponseEnvelope[GetCurrentModelPhysicsResponseData]):
    """当前模型物理配置响应信封。"""


class SetCurrentModelPhysicsRequestData(VTSEmptyData):
    """覆盖当前模型物理设置。"""

    strength_overrides: list[PhysicsOverride] = Field(default_factory=list, alias="strengthOverrides", description="物理强度覆盖项。")
    wind_overrides: list[PhysicsOverride] = Field(default_factory=list, alias="windOverrides", description="风力覆盖项。")


class SetCurrentModelPhysicsRequest(VTSRequestEnvelope[SetCurrentModelPhysicsRequestData]):
    """覆盖当前模型物理设置请求。"""

    message_type: str = Field(default="SetCurrentModelPhysicsRequest", alias="messageType", description="请求暂时覆盖物理强度/风力设置。")


class SetCurrentModelPhysicsResponse(VTSResponseEnvelope[VTSEmptyData]):
    """覆盖当前模型物理设置响应。"""
