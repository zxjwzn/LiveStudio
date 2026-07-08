"""配置编辑器常量"""

from __future__ import annotations

from typing import Any, Final

# SpinBox 无界时的默认范围(Qt 需要有限 range)。
INT_MIN: Final[int] = -2_147_483_648
INT_MAX: Final[int] = 2_147_483_647
FLOAT_MIN: Final[float] = -1.0e12
FLOAT_MAX: Final[float] = 1.0e12

ERROR_COLOR: Final[str] = "#EF4444"
INDENT_STEP: Final[int] = 16
INDENT_MAX: Final[int] = 64

PRIMITIVE_LABEL: Final[dict[Any, str]] = {
    str: "文本",
    int: "整数",
    float: "小数",
    bool: "开关",
}

NONE_TYPE: Final[type[None]] = type(None)
