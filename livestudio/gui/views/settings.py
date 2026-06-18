"""设置页。

GUI 自身设置（非后端配置），当前留空占位。预留分组：外观、行为、关于。
"""

from __future__ import annotations

import flet as ft

from ..components.placeholder import Placeholder
from ..core.base_view import BaseView


class SettingsView(BaseView):
    """设置视图：P1 留空占位。"""

    def build_content(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text("设置", size=22, weight=ft.FontWeight.W_600),
                Placeholder(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    title="GUI 设置",
                    subtitle="外观 / 行为 / 关于 —— 后续阶段填充",
                ),
            ],
            spacing=14,
            expand=True,
        )
