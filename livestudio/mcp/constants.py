"""MCP 常量"""

from typing import Final

LIST_PLATFORMS: Final[str] = "list_platforms"
SWITCH_PLATFORM: Final[str] = "switch_platform"
GET_ACTIVE_PLATFORM: Final[str] = "get_active_platform"
BUILTIN_NAMES: Final[frozenset[str]] = frozenset({LIST_PLATFORMS, SWITCH_PLATFORM, GET_ACTIVE_PLATFORM})
# 「固有」分两类,职责不同:
#  - 元信息(list/switch/get_active,见上 BUILTIN_NAMES):手写于 server._call_builtin,与平台
#    无关、无需 active、不注入状态。
#  - 通用动词(connect/情绪/控制器等):以 @tool(builtin=True) 标记、在 PlatformToolset 基类
#    反射声明,走 active toolset.call + runtime_context 注入(见 toolset.py)。不在此集合。

TOOL_MARK: Final[str] = "__mcp_tool_meta__"
ARGS_HEADERS: Final[tuple[str, ...]] = ("Args:", "Arguments:", "参数:", "参数：")
