"""LiveStudio MCP 服务

把已构造的各平台 app 以 MCP 工具的形式开放给 LLM。坐在 app 层之上,与 gui/ 平级:只调
app 公开方法,不创建/不组装任何后端(平台工具集由装配点用既有 app 构造后注入)。

工具可见性:恒定全表 = 各登记平台的全部工具(通用动词 + 特有工具)。当前仅登记单平台时
直接路由到该平台;多平台登记时要求工具名全局唯一,调用时按名解析到所属平台。
不再提供 list_platforms / switch_platform / get_active_platform。

镜像 gui/bridge/service_bridge.py 的聚合 + 生命周期角色;传输用 Streamable HTTP(app 常驻,
作为 in-process asyncio 服务复用同一事件循环)。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Sequence
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
from .registry import PlatformToolsetRegistration
from .toolset import PlatformToolset

# uvicorn 停机宽限期(秒):MCP 客户端长连 SSE 流不会被主动断开,设此上限保证
# _stop_transport 的 await task 必然结束、GUI 关窗不被卡住(见 _start_transport)。
_GRACEFUL_SHUTDOWN_TIMEOUT: Final[int] = 1


def _to_tool_result(value: object, *, context: str = "") -> mcp_types.CallToolResult:
    """把工具方法的返回值规范化为 MCP CallToolResult。

    str → 单个文本块;其余(list/dict 等)→ JSON 文本块,dict 额外作为 structuredContent。
    context 非空时作为独立文本块追加——承载平台实时状态(动态注入)。
    """

    if isinstance(value, str):
        content: list[mcp_types.ContentBlock] = [mcp_types.TextContent(type="text", text=value)]
        structured = None
    else:
        content = [mcp_types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False))]
        structured = value if isinstance(value, dict) else None
    if context:
        content.append(mcp_types.TextContent(type="text", text=f"[当前状态] {context}"))
    return mcp_types.CallToolResult(content=content, structuredContent=structured)


class LiveStudioMcpServer(AsyncServiceLifecycleMixin):
    """LiveStudio 的 MCP 服务:平台工具路由 + Streamable HTTP 传输。

    持有一组平台工具集登记(注入,非自建)。注册 low-level Server 的 list_tools / call_tool
    handler。生命周期(start/stop)起停 HTTP 传输。本类不认识任何具体平台。
    """

    def __init__(
        self,
        *,
        platforms: Sequence[PlatformToolsetRegistration],
        config_manager: ConfigManager[McpConfig] | None = None,
    ) -> None:
        self._registrations = list(platforms)
        self._by_name = {reg.name: reg for reg in self._registrations}
        if len(self._by_name) != len(self._registrations):
            raise ValueError("MCP 平台登记名重复")
        if not self._registrations:
            raise ValueError("MCP 至少需要登记一个平台")
        # 工具名 → 所属平台(全局唯一;多平台登记时冲突即报错)
        self._tool_owner: dict[str, PlatformToolsetRegistration] = {}
        for reg in self._registrations:
            for tool in reg.toolset.universal_tools() + reg.toolset.tools():
                if tool.name in self._tool_owner:
                    other = self._tool_owner[tool.name].name
                    raise ValueError(
                        f"MCP 工具名冲突: {tool.name!r} 同时属于 {other!r} 与 {reg.name!r}",
                    )
                self._tool_owner[tool.name] = reg
        # 监听设置由 config 管理:start 时 load,缺省 manager 指向 configs/mcp.yaml。
        self._config_manager = config_manager or ConfigManager(McpConfig, config_path("mcp.yaml"))

        self._server: Server = Server("livestudio")
        # session manager 每次起传输时新建:它 .run() 只能调用一次/实例,重启需换新实例。
        self._session_manager: StreamableHTTPSessionManager | None = None
        self._uvicorn: uvicorn.Server | None = None
        # 传输全生命周期收进单个专用任务(见 _start_transport):enter/exit cancel scope 同任务。
        self._transport_task: asyncio.Task[None] | None = None

        self._register_handlers()

    @property
    def config(self) -> McpConfig:
        """返回当前 MCP 监听配置快照(host / port)。"""

        return self._config_manager.config

    @property
    def endpoint_url(self) -> str:
        """返回 MCP client 应连接的 Streamable HTTP 端点(带尾斜杠)。"""

        cfg = self._config_manager.config
        return f"http://{cfg.host}:{cfg.port}/mcp/"

    def platform_tools(self) -> list[tuple[str, str, list[mcp_types.Tool]]]:
        """枚举所有登记平台及其工具,供 GUI 展示。

        返回每项为 (平台登记名, 平台说明, 该平台全部工具列表:通用 + 特有)。
        """

        return [
            (
                reg.name,
                reg.toolset.description,
                reg.toolset.universal_tools() + reg.toolset.tools(),
            )
            for reg in self._registrations
        ]

    def builtin_tools(self) -> list[mcp_types.Tool]:
        """返回通用动词定义(供 GUI 展示);取首个登记平台的 universal_tools(各平台相同)。"""

        return list(self._registrations[0].toolset.universal_tools())

    def _resolve_toolset(self, name: str) -> PlatformToolset:
        reg = self._tool_owner.get(name)
        if reg is None:
            raise ValueError(f"未知工具：{name}")
        return reg.toolset

    async def apply_config(self, config: McpConfig) -> None:
        """校验并写入新的监听配置,持久化后按需重启传输使其生效。

        host/port 变化需重建 HTTP 服务才生效:运行中则原地重启传输,未运行则只落盘。
        """

        validated = McpConfig.model_validate(config.model_dump())
        self._config_manager.config.host = validated.host
        self._config_manager.config.port = validated.port
        await self._config_manager.save()
        if self.is_started:
            await self._restart_transport()

    def _register_handlers(self) -> None:
        """注册 list_tools / call_tool handler(薄壳,逻辑在各 _*_impl 方法内,便于直测)。"""

        @self._server.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            return self._list_tools_impl()

        @self._server.call_tool()
        async def _call_tool(name: str, arguments: dict[str, object]) -> mcp_types.CallToolResult:
            return await self._dispatch_tool(name, arguments)

    def _list_tools_impl(self) -> list[mcp_types.Tool]:
        """对 LLM 可见的工具列表:全部登记平台的通用动词 + 特有工具(恒定全表)。

        通用动词平台无关,只取首个登记平台的版本,避免重复名。
        """

        tools = list(self._registrations[0].toolset.universal_tools())
        for reg in self._registrations:
            tools.extend(reg.toolset.tools())
        return tools

    async def _dispatch_tool(self, name: str, arguments: dict[str, object]) -> mcp_types.CallToolResult:
        """按工具名解析所属平台并调用,结果注入该平台 runtime_context。"""

        toolset = self._resolve_toolset(name)
        try:
            result = await toolset.call(name, arguments)
        except KeyError as exc:
            raise ValueError(f"当前平台无此工具：{name}") from exc
        context = await toolset.runtime_context()
        return _to_tool_result(result, context=context)

    # --- 传输与生命周期(Streamable HTTP,in-process) ---

    def _build_asgi_app(self, session_manager: StreamableHTTPSessionManager) -> Starlette:
        """构建挂载 MCP Streamable HTTP 端点的 ASGI 应用(端点路径 /mcp/)。"""

        async def _handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
            await session_manager.handle_request(scope, receive, send)

        return Starlette(routes=[Mount("/mcp", app=_handle_mcp)])

    async def _do_start(self) -> None:
        """加载监听配置并启动 Streamable HTTP 传输。"""

        await self._config_manager.load()
        await self._start_transport()

    async def _start_transport(self) -> None:
        """按当前配置起传输:在一个专用任务里跑 session manager + uvicorn 服务。

        关键约束:`session_manager.run()` 进入的是 anyio cancel scope,**进入与退出必须在
        同一任务**,否则跨任务退出会抛「exit cancel scope in a different task」。而 start 可能
        由主 GUI 任务调用、stop/重启可能由 run_guarded 任务调用——故把整段传输生命周期收进
        单个 `_run_transport` 任务自管 enter/exit,start/stop 只与该任务交互(置 should_exit +
        await),不直接进出 cancel scope。
        """

        cfg = self._config_manager.config
        session_manager = StreamableHTTPSessionManager(app=self._server)
        self._session_manager = session_manager

        config = uvicorn.Config(
            self._build_asgi_app(session_manager),
            host=cfg.host,
            port=cfg.port,
            log_level="warning",
            lifespan="off",
            # MCP 客户端持有长连 SSE 流;uvicorn 默认 timeout_graceful_shutdown=None 会
            # 在 shutdown() 里死等连接关闭,导致 GUI 点 X 关窗时 _stop_transport 的
            # await task 永不返回、窗口无法关闭。设上限让停机有界:宽限期内未结束即强取消。
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
        )
        server = uvicorn.Server(config)
        self._uvicorn = server
        self._transport_task = asyncio.create_task(self._run_transport(session_manager, server))

        # 等到 uvicorn 真正开始监听再返回,使「应用并重启」完成时端点确已就绪;若任务提前
        # 失败则把异常抛出(await 已结束的任务即重新抛出其异常)。
        while not server.started:
            if self._transport_task.done():
                await self._transport_task
                return
            await asyncio.sleep(0.02)
        logger.success("LiveStudio MCP 服务已启动: {}", self.endpoint_url)

    @staticmethod
    async def _run_transport(session_manager: StreamableHTTPSessionManager, server: uvicorn.Server) -> None:
        """专用任务:在本任务内进入/退出 session manager 的 cancel scope 并跑 uvicorn。"""

        async with session_manager.run():
            await server.serve()

    async def _restart_transport(self) -> None:
        """以新配置原地重启传输(不动生命周期 _started):先收旧传输,再按新配置起。"""

        await self._stop_transport()
        await self._start_transport()
        logger.info("LiveStudio MCP 服务已按新配置重启")

    async def _stop_transport(self) -> None:
        """收起当前传输:置 should_exit 让 serve 退出,await 专用任务收尾(cancel scope 在该任务内退出)。"""

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
        """停止传输并保存监听配置(终止入口)。"""

        await self._stop_transport()
        with contextlib.suppress(Exception):
            await self._config_manager.save()
        logger.info("LiveStudio MCP 服务已停止")
