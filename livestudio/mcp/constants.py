"""MCP 常量"""

from typing import Final

LIST_PLATFORMS: Final[str] = "list_platforms"
SWITCH_PLATFORM: Final[str] = "switch_platform"
GET_ACTIVE_PLATFORM: Final[str] = "get_active_platform"
BUILTIN_NAMES: Final[frozenset[str]] = frozenset({LIST_PLATFORMS, SWITCH_PLATFORM, GET_ACTIVE_PLATFORM})

TOOL_MARK: Final[str] = "__mcp_tool_meta__"
ARGS_HEADERS: Final[tuple[str, ...]] = ("Args:", "Arguments:", "参数:", "参数：")
