"""MCP 层:把平台控制能力以 MCP 工具开放给 LLM

坐在 app 层之上,与 gui/ 平级。只调 app 公开方法,不创建/不组装后端:平台工具集由顶层
入口用既有 app 实例构造后,经 PlatformToolsetRegistration 注入 LiveStudioMcpServer。
"""

from .config import McpConfig
from .registry import PlatformToolsetRegistration
from .server import LiveStudioMcpServer
from .toolset import PlatformToolset, tool

__all__ = [
    "LiveStudioMcpServer",
    "McpConfig",
    "PlatformToolset",
    "PlatformToolsetRegistration",
    "tool",
]
