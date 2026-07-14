"""MCP 服务的 GUI 配置桥接。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from livestudio.gui.core import run_guarded
from livestudio.mcp import LiveStudioMcpServer, McpConfig
from livestudio.utils.log import logger


class McpBridge(QObject):
    """MCP 服务的监听配置与运行态桥接。"""

    configApplied = Signal(str, int)  # 应用成功后的 host, port
    errorOccurred = Signal(str)

    def __init__(self, server: LiveStudioMcpServer, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = server

    def endpoint_url(self) -> str:
        """当前 MCP 端点地址(供展示与复制)"""

        return self._server.endpoint_url

    def current_config(self) -> McpConfig:
        """当前监听配置快照(host / port)"""

        return self._server.config

    def is_running(self) -> bool:
        """MCP 服务是否正在运行"""

        return self._server.is_started

    def apply_config(self, host: str, port: int) -> None:
        """应用并持久化监听配置(运行中则重启传输);成功发 configApplied,失败发 errorOccurred。"""

        run_guarded(self._apply_config(host, port), on_error=self._on_error)

    async def _apply_config(self, host: str, port: int) -> None:
        config = McpConfig(host=host, port=port)
        await self._server.apply_config(config)
        self.configApplied.emit(config.host, config.port)

    def _on_error(self, exc: BaseException) -> None:
        logger.error("MCP 配置应用失败: {}", exc)
        self.errorOccurred.emit(str(exc))
