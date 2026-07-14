"""空 MCP 服务框架测试。"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from livestudio.config import ConfigManager
from livestudio.mcp import LiveStudioMcpServer
from livestudio.mcp.config import McpConfig


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_server(port: int, config_path: Path) -> LiveStudioMcpServer:
    return LiveStudioMcpServer(
        config_manager=ConfigManager(
            McpConfig,
            config_path,
            default_config=McpConfig(host="127.0.0.1", port=port),
        ),
    )


async def test_client_can_initialize_and_list_empty_tools(tmp_path: Path) -> None:
    server = _make_server(_free_port(), tmp_path / "mcp.yaml")
    await server.start()

    async def _check_client() -> None:
        async with (
            streamable_http_client(server.endpoint_url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
            assert result.tools == []

    try:
        await asyncio.wait_for(_check_client(), timeout=5)
    finally:
        await server.stop()
