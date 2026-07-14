"""MCP 服务桥接

包装 LiveStudioMcpServer,把「工具清单 / 监听配置 / 运行态」暴露为 GUI 可用的同步读取
方法 + 应用配置的异步动作 + Qt 信号。视图只依赖本桥接,不直接 import MCP 后端类型。

工具清单与平台无关、随服务构造即固定(由各 toolset 的 @tool 方法反射得到),故同步读取;
监听配置的应用涉及落盘与传输重启,走 run_guarded 异步调度。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from livestudio.gui.core import run_guarded
from livestudio.mcp import LiveStudioMcpServer, McpConfig
from livestudio.utils.log import logger


@dataclass(frozen=True, slots=True)
class ToolInfo:
    """单个 MCP 工具的展示信息(名称 + 描述)"""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class ToolGroup:
    """一组工具:通用动词,或某平台的工具集"""

    title: str  # 分组标题(如 "通用工具" / 平台展示名)
    subtitle: str  # 分组副标题
    tools: list[ToolInfo]


class McpBridge(QObject):
    """MCP 服务的 GUI 桥接:工具清单 + 监听配置读写 + 运行态信号"""

    configApplied = Signal(str, int)  # 应用成功后的 host, port
    errorOccurred = Signal(str)

    _UNIVERSAL_TITLE = "通用工具"
    _UNIVERSAL_SUBTITLE = (
        "连接、待机动画、情绪与表演时间线(add_event → enqueue_draft)。"
        "无需切换平台;登记的平台能力直接可用。"
    )

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

    def tool_groups(self) -> list[ToolGroup]:
        """全部工具分组:通用动词一组 + 每个平台特有工具一组。"""

        groups = [
            ToolGroup(
                title=self._UNIVERSAL_TITLE,
                subtitle=self._UNIVERSAL_SUBTITLE,
                tools=[ToolInfo(tool.name, tool.description or "") for tool in self._server.builtin_tools()],
            )
        ]
        for name, description, tools in self._server.platform_tools():
            # platform_tools 现含通用+特有;展示时只列特有,避免与通用组重复
            universal_names = {t.name for t in self._server.builtin_tools()}
            specific = [t for t in tools if t.name not in universal_names]
            if not specific:
                continue
            groups.append(
                ToolGroup(
                    title=name,
                    subtitle=description,
                    tools=[ToolInfo(tool.name, tool.description or "") for tool in specific],
                )
            )
        return groups

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
