"""仪表盘页（P1 占位）。

P3 阶段将填充连接状态、实时电平、控制器启停与快速表情。
当前仅占位，验证导航与主题。
"""

from __future__ import annotations

import flet as ft

from ..components.placeholder import Placeholder
from ..core.base_view import BaseView


class DashboardView(BaseView):
    """仪表盘视图。"""

    def build_content(self) -> ft.Control:
        return Placeholder(
            icon=ft.Icons.DASHBOARD_OUTLINED,
            title="仪表盘",
            subtitle="连接状态 · 实时电平 · 控制器启停 · 快速表情（P3 实现）",
        )
