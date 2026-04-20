"""用于 VTube Studio API 广播的 UDP 发现模型。"""

from __future__ import annotations

from pydantic import Field

from .base import VTSBaseModel, VTSResponseEnvelope


class VTubeStudioAPIStateBroadcastData(VTSBaseModel):
    """VTube Studio UDP 广播负载。"""

    active: bool = Field(description="VTube Studio API 当前是否激活。")
    port: int = Field(ge=1, le=65535, description="VTube Studio WebSocket 监听端口。")
    instance_id: str = Field(alias="instanceID", description="当前 VTube Studio 进程实例 ID。")
    window_title: str = Field(alias="windowTitle", description="当前窗口标题。")


class VTubeStudioAPIStateBroadcast(VTSResponseEnvelope[VTubeStudioAPIStateBroadcastData]):
    """VTube Studio API 状态 UDP 广播。"""