"""AppState：唯一全局状态容器

由 ServiceBridge 创建并注入所有视图。后端事件经桥接层转换为 view-model
后写入此处的 Observable，视图订阅渲染，形成单向数据流。
"""

from __future__ import annotations

from .observable import Observable, ObservableList
from .view_models import (
    AudioDeviceVM,
    AudioLevelVM,
    AudioSourceKind,
    ControllerVM,
    DiscoveredEndpointVM,
    ExpressionVM,
    LogEntryVM,
    ModelConfigVM,
    PlatformStatusVM,
)


class AppState:
    """聚合全部 Observable 的应用状态。"""

    def __init__(self) -> None:
        # —— 平台 ——
        self.platforms: ObservableList[PlatformStatusVM] = ObservableList([])
        self.active_platform_id: Observable[str] = Observable("")
        self.discovered: ObservableList[DiscoveredEndpointVM] = ObservableList([])
        self.model_config: Observable[ModelConfigVM | None] = Observable(None)

        # —— 动画控制器 / 表情（属于当前 active 平台）——
        self.controllers: ObservableList[ControllerVM] = ObservableList([])
        self.expressions: ObservableList[ExpressionVM] = ObservableList([])

        # —— 音频 ——
        self.audio_level: Observable[AudioLevelVM] = Observable(AudioLevelVM())
        self.audio_devices: ObservableList[AudioDeviceVM] = ObservableList([])
        self.audio_source: Observable[AudioSourceKind] = Observable(AudioSourceKind.MICROPHONE)

        # —— 日志 ——
        self.logs: ObservableList[LogEntryVM] = ObservableList([])

        # —— GUI 自身设置（settings 页，目前留空）——
        self.settings: Observable[dict] = Observable({})

    def platform_status(self, pid: str) -> PlatformStatusVM | None:
        """按平台 id 取当前状态快照。"""

        return next((p for p in self.platforms.value if p.platform_id == pid), None)

    def active_platform_status(self) -> PlatformStatusVM | None:
        """取当前激活平台的状态快照。"""

        return self.platform_status(self.active_platform_id.value)
