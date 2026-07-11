"""字幕服务 GUI 桥接

包装 SubtitleService:同步读配置/端点/运行态;异步 apply 配置并发信号。
视图只依赖本桥接,不直接 import 字幕后端类型。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from livestudio.gui.core import run_guarded
from livestudio.services.subtitle import SubtitleConfig, SubtitleService
from livestudio.utils.log import logger


class SubtitleBridge(QObject):
    """字幕服务的 GUI 桥接:配置读写 + 运行态 + 端点展示"""

    configApplied = Signal()
    errorOccurred = Signal(str)

    def __init__(self, service: SubtitleService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service

    def endpoint_url(self) -> str:
        return self._service.endpoint_url

    def ws_url(self) -> str:
        return self._service.ws_url

    def current_config(self) -> SubtitleConfig:
        return self._service.config

    def is_running(self) -> bool:
        return self._service.is_started and self._service.config.enabled

    def apply_config(self, config: SubtitleConfig) -> None:
        """应用并持久化配置(运行中按需重启传输)"""

        run_guarded(self._apply_config(config), on_error=self._on_error)

    async def _apply_config(self, config: SubtitleConfig) -> None:
        await self._service.apply_config(config)
        self.configApplied.emit()

    def _on_error(self, exc: BaseException) -> None:
        logger.error("字幕配置应用失败: {}", exc)
        self.errorOccurred.emit(str(exc))
