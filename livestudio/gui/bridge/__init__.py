"""GUI 桥接层。

后端服务与 AppState 之间的唯一通道：后端事件经此转为 view-model 写入状态，
UI 意图经此转为后端 async 调用。

- ServiceBridge：总装配器与生命周期。
- AudioController / LogController：音频电平、日志的桥接。
- platforms/：平台适配器（PlatformAdapter 抽象 + 各平台实现）。
"""

from __future__ import annotations

from .audio_controller import AudioController
from .log_controller import LogController
from .platforms.base import PlatformAdapter, PlatformContext
from .platforms.vtube_studio import VTubeStudioAdapter
from .service_bridge import ServiceBridge

__all__ = [
    "AudioController",
    "LogController",
    "PlatformAdapter",
    "PlatformContext",
    "ServiceBridge",
    "VTubeStudioAdapter",
]
