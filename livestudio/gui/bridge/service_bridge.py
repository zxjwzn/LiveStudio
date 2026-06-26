"""服务桥接:聚合后端生命周期

持有后端三件套与各子桥接,提供 startup/shutdown 的统一编排。startup 让音频即时可用
(默认仪表盘电平有信号);shutdown 有序停机且隔离异常,不阻塞窗口关闭。
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from livestudio.app import VTubeStudioApp
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.utils.log import logger

from .audio_bridge import AudioController
from .log_bridge import LogController
from .vtubestudio_bridge import VTubeStudioPlatformBridge


class ServiceBridge(QObject):
    """后端生命周期与子桥接的聚合器"""

    def __init__(
        self,
        *,
        audio_router: AudioStreamRouter,
        vtubestudio_app: VTubeStudioApp,
        log_level: str = "INFO",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._audio_router = audio_router
        self._vtubestudio_app = vtubestudio_app

        self.audio = AudioController(audio_router, self)
        self.logs = LogController(self)
        self.vtubestudio = VTubeStudioPlatformBridge(vtubestudio_app, self)
        self._log_level = log_level

    async def startup(self) -> None:
        """注册日志 sink 并 eager 启动音频(切到麦克风,使电平即时可见)"""

        self.logs.start(self._log_level)
        await self._audio_router.start()
        await self._audio_router.switch_source(AudioSourceKind.MICROPHONE)
        self.audio.start_metering()

    async def shutdown(self) -> None:
        """有序停机:停电平推送 → 停 VTS 应用 → 停音频路由 → 停日志 sink"""

        self.audio.stop_metering()
        for name, service in (
            ("VTubeStudioApp", self._vtubestudio_app),
            ("AudioStreamRouter", self._audio_router),
        ):
            try:
                await service.stop()
            except Exception:
                logger.exception("停止 {} 失败,已隔离继续关闭", name)
        self.logs.stop()
