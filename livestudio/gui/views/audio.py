"""音频流页（P1 占位）。

P5 阶段将填充实时电平条与音频源切换。
"""

from __future__ import annotations

import flet as ft

from ..components.placeholder import Placeholder
from ..core.base_view import BaseView


class AudioView(BaseView):
    """音频流视图。"""

    def build_content(self) -> ft.Control:
        return Placeholder(
            icon=ft.Icons.GRAPHIC_EQ,
            title="音频流",
            subtitle="实时电平 · 音频源切换（P5 实现）",
        )
