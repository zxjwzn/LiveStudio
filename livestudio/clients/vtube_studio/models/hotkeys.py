"""Hotkey and expression related request/response models."""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import ExpressionState, Hotkey


class HotkeysInCurrentModelRequestData(VTSEmptyData):
    """获取当前模型或指定模型/Live2D 道具热键。"""

    model_id: str | None = Field(default=None, alias="modelID", description="可选模型 ID；为空时使用当前模型。")
    live2d_item_file_name: str | None = Field(default=None, alias="live2DItemFileName", description="可选 Live2D 道具文件名；当提供 model_id 时会被忽略。")


class HotkeysInCurrentModelRequest(VTSRequestEnvelope[HotkeysInCurrentModelRequestData]):
    """查询热键列表请求。"""

    message_type: str = Field(default="HotkeysInCurrentModelRequest", alias="messageType", description="请求模型或道具的热键列表。")


class HotkeysInCurrentModelResponseData(VTSEmptyData):
    """热键列表响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="目标模型当前是否加载。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    available_hotkeys: list[Hotkey] = Field(alias="availableHotkeys", description="可用热键列表。")


class HotkeysInCurrentModelResponse(VTSResponseEnvelope[HotkeysInCurrentModelResponseData]):
    """热键列表响应信封。"""


class HotkeyTriggerRequestData(VTSEmptyData):
    """触发热键。"""

    hotkey_id: str = Field(alias="hotkeyID", description="热键唯一 ID，或热键名称。")
    item_instance_id: str | None = Field(default=None, alias="itemInstanceID", description="可选 Live2D 道具实例 ID。")


class HotkeyTriggerRequest(VTSRequestEnvelope[HotkeyTriggerRequestData]):
    """触发热键请求。"""

    message_type: str = Field(default="HotkeyTriggerRequest", alias="messageType", description="请求执行一个热键。")


class HotkeyTriggerResponseData(VTSEmptyData):
    """热键触发结果。"""

    hotkey_id: str = Field(alias="hotkeyID", description="实际执行的热键唯一 ID。")


class HotkeyTriggerResponse(VTSResponseEnvelope[HotkeyTriggerResponseData]):
    """热键触发响应。"""


class ExpressionStateRequestData(VTSEmptyData):
    """查询表达式状态。"""

    details: bool = Field(default=False, description="是否返回热键引用与参数明细。")
    expression_file: str | None = Field(default=None, alias="expressionFile", description="可选表达式文件名；为空则返回全部表达式。")


class ExpressionStateRequest(VTSRequestEnvelope[ExpressionStateRequestData]):
    """表达式状态请求。"""

    message_type: str = Field(default="ExpressionStateRequest", alias="messageType", description="请求表达式激活状态。")


class ExpressionStateResponseData(VTSEmptyData):
    """表达式状态响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载模型。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    expressions: list[ExpressionState] = Field(description="表达式状态列表。")


class ExpressionStateResponse(VTSResponseEnvelope[ExpressionStateResponseData]):
    """表达式状态响应信封。"""


class ExpressionActivationRequestData(VTSEmptyData):
    """激活或关闭表达式。"""

    expression_file: str = Field(alias="expressionFile", description="目标表达式文件名，必须以 `.exp3.json` 结尾。")
    fade_time: float | None = Field(default=None, alias="fadeTime", ge=0, le=2, description="淡入时长，秒。默认 0.25。")
    active: bool = Field(description="`true` 激活表达式，`false` 关闭表达式。")


class ExpressionActivationRequest(VTSRequestEnvelope[ExpressionActivationRequestData]):
    """表达式激活控制请求。"""

    message_type: str = Field(default="ExpressionActivationRequest", alias="messageType", description="请求直接激活或关闭表达式。")


class ExpressionActivationResponse(VTSResponseEnvelope[VTSEmptyData]):
    """表达式激活响应。"""
