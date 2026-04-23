"""通用信息请求/响应模型。"""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope


class StatisticsRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取当前 VTube Studio 统计信息。"""

    message_type: str = Field(
        default="StatisticsRequest",
        alias="messageType",
        description="请求运行时统计信息。",
    )
    data: VTSEmptyData = Field(
        default_factory=VTSEmptyData,
        description="该请求无需额外参数。",
    )


class StatisticsResponseData(VTSEmptyData):
    """统计信息响应。"""

    uptime: int = Field(description="应用启动后的毫秒数。")
    framerate: int = Field(description="当前渲染帧率。")
    v_tube_studio_version: str = Field(
        alias="vTubeStudioVersion",
        description="VTube Studio 版本号。",
    )
    allowed_plugins: int = Field(alias="allowedPlugins", description="已授权插件数量。")
    connected_plugins: int = Field(
        alias="connectedPlugins",
        description="当前已连接插件数量。",
    )
    started_with_steam: bool = Field(
        alias="startedWithSteam",
        description="是否通过 Steam 启动。",
    )
    window_width: int = Field(alias="windowWidth", description="窗口宽度，像素。")
    window_height: int = Field(alias="windowHeight", description="窗口高度，像素。")
    window_is_fullscreen: bool = Field(
        alias="windowIsFullscreen",
        description="窗口是否为全屏。",
    )


class StatisticsResponse(VTSResponseEnvelope[StatisticsResponseData]):
    """统计信息响应信封。"""


class VTSFolderInfoRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取 VTS 目录信息。"""

    message_type: str = Field(
        default="VTSFolderInfoRequest",
        alias="messageType",
        description="请求 StreamingAssets 下的关键目录名。",
    )
    data: VTSEmptyData = Field(
        default_factory=VTSEmptyData,
        description="该请求无需额外参数。",
    )


class VTSFolderInfoResponseData(VTSEmptyData):
    """目录信息响应。"""

    models: str = Field(description="模型目录名称。")
    backgrounds: str = Field(description="背景目录名称。")
    items: str = Field(description="道具目录名称。")
    config: str = Field(description="配置目录名称。")
    logs: str = Field(description="日志目录名称。")
    backup: str = Field(description="备份目录名称。")


class VTSFolderInfoResponse(VTSResponseEnvelope[VTSFolderInfoResponseData]):
    """目录信息响应信封。"""


class FaceFoundRequest(VTSRequestEnvelope[VTSEmptyData]):
    """查询当前追踪器是否检测到人脸。"""

    message_type: str = Field(
        default="FaceFoundRequest",
        alias="messageType",
        description="请求当前是否检测到人脸。",
    )
    data: VTSEmptyData = Field(
        default_factory=VTSEmptyData,
        description="该请求无需额外参数。",
    )


class FaceFoundResponseData(VTSEmptyData):
    """人脸检测状态。"""

    found: bool = Field(description="当前追踪器是否检测到人脸。")


class FaceFoundResponse(VTSResponseEnvelope[FaceFoundResponseData]):
    """人脸检测响应信封。"""
