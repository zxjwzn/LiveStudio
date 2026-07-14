"""MCP 服务停机有界性回归

根因:GUI 点 X 关窗走 _shutdown_and_quit -> mcp_server.stop() -> _stop_transport 的
await task(uvicorn.serve)。若有 MCP 客户端持有长连 SSE 流,uvicorn 默认
timeout_graceful_shutdown=None 会在 shutdown() 的 _wait_tasks_to_complete 里
`while self.server_state.connections: sleep` 死等,serve() 永不返回,窗口卡死无法关闭、
并伴随「ASGI callable returned without completing response」日志。

修复:在 uvicorn.Config 设 timeout_graceful_shutdown 上限(见 _GRACEFUL_SHUTDOWN_TIMEOUT),
使停机有界。本测试直接守卫该配置项--无修复时为 None,测试失败。

客户端握手与空工具列表由 test_mcp_server 覆盖；本模块只守卫停机配置。
"""

from __future__ import annotations

import socket
from pathlib import Path

from livestudio.config import ConfigManager
from livestudio.mcp import LiveStudioMcpServer
from livestudio.mcp.config import McpConfig


def _free_port() -> int:
    """让 OS 分配一个空闲端口,关闭监听套接字后交由 uvicorn 复用(存在轻微竞态,测试可接受)。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server(port: int, config_path: Path) -> LiveStudioMcpServer:
    config_manager = ConfigManager(
        McpConfig,
        config_path,
        default_config=McpConfig(host="127.0.0.1", port=port),
    )
    return LiveStudioMcpServer(config_manager=config_manager)


async def test_uvicorn_config_bounded_graceful_shutdown(tmp_path: Path) -> None:
    """启动后 uvicorn.Config.timeout_graceful_shutdown 必须为正数(非 None)。

    None = uvicorn 死等长连 -> GUI 关窗卡死(回归点)。有界正值保证 _stop_transport 的
    await task 必然结束、窗口可关闭。
    """

    port = _free_port()
    server = _make_server(port, tmp_path / "mcp.yaml")
    await server.start()
    try:
        uv = server._uvicorn  # noqa: SLF001  # 直触内部配置断言
        assert uv is not None, "start() 后 _uvicorn 必已就绪"
        timeout = uv.config.timeout_graceful_shutdown
        assert timeout is not None, "timeout_graceful_shutdown 未设置:uvicorn 会死等长连,GUI 关窗卡死"
        assert timeout > 0, f"timeout_graceful_shutdown 须为正数,实为 {timeout}"
    finally:
        # 无已连接客户端,stop() 立即返回(回归只发生在有长连时)
        await server.stop()
