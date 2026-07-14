"""空 MCP 服务框架。

保留 Streamable HTTP 传输、监听配置和生命周期，不注册任何业务工具。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Final

import mcp.types as mcp_types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from livestudio.config import ConfigManager
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.utils.log import logger
from livestudio.utils.paths import config_path

from .config import McpConfig

# MCP 客户端可能持有长连接，限制停机等待时间，避免 GUI 关闭时一直阻塞。
_GRACEFUL_SHUTDOWN_TIMEOUT: Final[int] = 1


class LiveStudioMcpServer(AsyncServiceLifecycleMixin):
    """只提供协议端点和生命周期的空 MCP 服务。"""

    def __init__(self, *, config_manager: ConfigManager[McpConfig] | None = None) -> None:
        self._config_manager = config_manager or ConfigManager(McpConfig, config_path("mcp.yaml"))
        self._server: Server = Server("livestudio")
        self._session_manager: StreamableHTTPSessionManager | None = None
        self._uvicorn: uvicorn.Server | None = None
        self._transport_task: asyncio.Task[None] | None = None
        self._register_handlers()

    @property
    def config(self) -> McpConfig:
        """返回当前监听配置。"""

        return self._config_manager.config

    @property
    def endpoint_url(self) -> str:
        """返回 Streamable HTTP 端点。"""

        cfg = self._config_manager.config
        return f"http://{cfg.host}:{cfg.port}/mcp/"

    async def apply_config(self, config: McpConfig) -> None:
        """保存监听配置，运行中立即重启传输。"""

        validated = McpConfig.model_validate(config.model_dump())
        await self._config_manager.save(validated)
        if self.is_started:
            await self._restart_transport()

    def _register_handlers(self) -> None:
        """注册空工具列表，保留 MCP tools 能力框架。"""

        @self._server.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            return self._list_tools_impl()

    @staticmethod
    def _list_tools_impl() -> list[mcp_types.Tool]:
        return []

    def _build_asgi_app(self, session_manager: StreamableHTTPSessionManager) -> Starlette:
        """构建挂载在 /mcp/ 的 ASGI 应用。"""

        async def _handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
            await session_manager.handle_request(scope, receive, send)

        return Starlette(routes=[Mount("/mcp", app=_handle_mcp)])

    async def _do_start(self) -> None:
        await self._config_manager.load()
        await self._start_transport()

    async def _start_transport(self) -> None:
        cfg = self._config_manager.config
        session_manager = StreamableHTTPSessionManager(app=self._server)
        self._session_manager = session_manager

        config = uvicorn.Config(
            self._build_asgi_app(session_manager),
            host=cfg.host,
            port=cfg.port,
            log_level="warning",
            lifespan="off",
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
        )
        server = uvicorn.Server(config)
        self._uvicorn = server
        self._transport_task = asyncio.create_task(self._run_transport(session_manager, server))

        while not server.started:
            if self._transport_task.done():
                await self._transport_task
                return
            await asyncio.sleep(0.02)
        logger.success("LiveStudio MCP 服务已启动: {}", self.endpoint_url)

    @staticmethod
    async def _run_transport(session_manager: StreamableHTTPSessionManager, server: uvicorn.Server) -> None:
        # anyio cancel scope 必须在创建它的同一任务中退出。
        async with session_manager.run():
            await server.serve()

    async def _restart_transport(self) -> None:
        await self._stop_transport()
        await self._start_transport()
        logger.info("LiveStudio MCP 服务已按新配置重启")

    async def _stop_transport(self) -> None:
        task = self._transport_task
        server = self._uvicorn
        self._transport_task = None
        self._uvicorn = None
        self._session_manager = None
        if server is not None:
            server.should_exit = True
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _do_stop(self) -> None:
        await self._stop_transport()
        with contextlib.suppress(Exception):
            await self._config_manager.save()
        logger.info("LiveStudio MCP 服务已停止")
