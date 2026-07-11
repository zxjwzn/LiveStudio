"""GUI 与后端之间的桥接层

视图只依赖本层的信号与方法,不直接 import 后端类型。桥接负责在 qasync 事件循环上
调度后端协程,并把跨线程回调(音频/日志)marshal 回 Qt。
"""

from .audio_bridge import AudioController
from .log_bridge import LogController, LogEntry
from .mcp_bridge import McpBridge, ToolGroup, ToolInfo
from .platform_bridge import (
    ConnectionState,
    ControllerEntry,
    ControllerSpec,
    EmotionSpec,
    ModelConfigEntry,
    PlatformBridge,
)
from .service_bridge import PlatformRegistration, ServiceBridge
from .subtitle_bridge import SubtitleBridge
from .vtubestudio_bridge import VTubeStudioPlatformBridge

__all__ = [
    "AudioController",
    "ConnectionState",
    "ControllerEntry",
    "ControllerSpec",
    "EmotionSpec",
    "LogController",
    "LogEntry",
    "McpBridge",
    "ModelConfigEntry",
    "PlatformBridge",
    "PlatformRegistration",
    "ServiceBridge",
    "SubtitleBridge",
    "ToolGroup",
    "ToolInfo",
    "VTubeStudioPlatformBridge",
]
