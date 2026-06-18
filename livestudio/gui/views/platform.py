"""平台页（P1 占位）。

P4 阶段将填充平台选择器、连接区与模型配置编辑器。
"""

from __future__ import annotations

import flet as ft

from ..components.placeholder import Placeholder
from ..core.base_view import BaseView


class PlatformView(BaseView):
    """平台视图。"""

    def build_content(self) -> ft.Control:
        return Placeholder(
            icon=ft.Icons.HUB_OUTLINED,
            title="平台",
            subtitle="连接 · LAN 发现 · 模型配置编辑（P4 实现）",
        )
