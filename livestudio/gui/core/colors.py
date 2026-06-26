"""设计系统色彩 token

集中 docs/gui-design/00 §3 的语义色,供状态徽标、日志级别、电平条等复用。
深色为默认主题;语义色在浅/深色下均保持可辨识。
"""

from typing import Final

# 主色板(00 §3.1)
PRIMARY: Final[str] = "#0F172A"
SECONDARY: Final[str] = "#1E293B"
BACKGROUND: Final[str] = "#020617"
TEXT: Final[str] = "#F8FAFC"
ACCENT_DEFAULT: Final[str] = "#22C55E"

# 状态语义色(连接态 / 日志级别共用)
SUCCESS: Final[str] = "#22C55E"  # 已连接 / 运行中 / 成功
WARNING: Final[str] = "#F59E0B"  # 重连中 / WARNING
ERROR: Final[str] = "#EF4444"  # 错误 / 断开错误 / ERROR
NEUTRAL: Final[str] = "#64748B"  # 断开(非错误) / DEBUG / 禁用
INFO: Final[str] = "#38BDF8"  # INFO / 提示
