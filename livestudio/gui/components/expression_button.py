"""快速表情按钮组件。

显示 emoji + 情绪名，点击触发对应情绪的表情解算。
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ..core.theme import PALETTE
from ..core.view_models import ExpressionVM


class ExpressionButton(ft.OutlinedButton):
    """单个快速表情触发按钮。"""

    def __init__(self, vm: ExpressionVM, *, on_trigger: Callable[[ExpressionVM], None]) -> None:
        label = f"{vm.emoji} {vm.display_name}".strip()
        super().__init__(
            text=label,
            on_click=lambda _e: on_trigger(vm),
            style=ft.ButtonStyle(
                color=PALETTE.text,
                bgcolor=PALETTE.surface_alt,
                side=ft.BorderSide(1, PALETTE.border),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )
