"""服务桥接:聚合后端生命周期

持有音频/日志子桥接与一组「平台登记」(后端 app + 对应 GUI 桥接成对)。startup 让
音频即时可用(默认仪表盘电平有信号);shutdown 有序停机且隔离异常,不阻塞窗口关闭。

平台以 PlatformRegistration 列表注入(由 app.py 工厂构造),本类不认识任何具体平台:
新增平台只在工厂多登记一项,startup/shutdown/platforms 全自动覆盖。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject

from livestudio.services import AudioStreamRouter
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.utils.log import logger

from .audio_bridge import AudioController
from .log_bridge import LogController
from .platform_bridge import PlatformBridge


@dataclass(frozen=True, slots=True)
class PlatformRegistration:
    """一个平台的登记项:后端应用 + 对应 GUI 桥接(成对,生命周期一起编排)。

    app 须实现统一异步生命周期(stop());bridge 是视图层消费的平台抽象。
    """

    name: str  # 停机日志用的可读名(如 "VTubeStudioApp")
    app: AsyncServiceLifecycleMixin
    bridge: PlatformBridge


class ServiceBridge(QObject):
    """后端生命周期与子桥接的聚合器"""

    def __init__(
        self,
        *,
        audio_router: AudioStreamRouter,
        platforms: Sequence[PlatformRegistration],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._audio_router = audio_router
        self._registrations = list(platforms)

        self.audio = AudioController(audio_router, self)
        self.logs = LogController(self)

        # 平台登记单一事实源:仪表盘/平台页按此列表渲染。
        self.platforms: list[PlatformBridge] = [reg.bridge for reg in self._registrations]

    async def startup(self) -> None:
        """注册日志 sink 并启动音频(按配置的激活源 config.source,使电平即时可见)"""

        self.logs.start()
        await self._audio_router.start()  # 启动配置里的激活源(不强制麦克风,尊重用户选择)
        self.audio.start_metering()

    async def shutdown(self) -> None:
        """有序停机:停电平推送 → 逐个停平台应用 → 停音频路由 → 停日志 sink。

        每个服务独立 try/except 隔离,单个停机失败不阻塞其余与窗口关闭。
        """

        self.audio.stop_metering()
        services: list[tuple[str, AsyncServiceLifecycleMixin]] = [
            (reg.name, reg.app) for reg in self._registrations
        ]
        services.append(("AudioStreamRouter", self._audio_router))
        for name, service in services:
            try:
                await service.stop()
            except Exception as exc:
                if _is_exception_group(exc):
                    logger.error("停止 {} 失败,已隔离继续关闭: {}", name, exc)
                    for index, sub_exc in enumerate(getattr(exc, "exceptions", ()), start=1):
                        logger.opt(exception=sub_exc).error("停止 {} 子异常 #{}: {}", name, index, sub_exc)
                else:
                    logger.exception("停止 {} 失败,已隔离继续关闭", name)
        self.logs.stop()


def _is_exception_group(exc: BaseException) -> bool:
    return isinstance(getattr(exc, "exceptions", None), tuple)
