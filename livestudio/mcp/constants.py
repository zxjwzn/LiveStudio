"""MCP 层常量

仅保留工具反射标记与 Args 段解析用表头;平台切换元工具已移除。
"""

from typing import Final

# @tool 装饰器在方法上 setattr 的标记属性名
TOOL_MARK: Final[str] = "__mcp_tool__"

# docstring 中 Args 段的合法标题(与 Google / NumPy 风格对齐)
ARGS_HEADERS: Final[frozenset[str]] = frozenset({"Args:", "Arguments:", "Parameters:"})
