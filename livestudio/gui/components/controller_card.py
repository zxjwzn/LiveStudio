"""动画控制器卡片组件。

显示单个控制器的状态点 + 名称 + 操作按钮：
- idle 型：根据运行状态显示启动/停止按钮。
- oneshot 型：显示触发按钮。
点击回调由调用方注入（通常转发到 bridge 适配器的异步意图）。
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ..core.theme import PALETTE, TYPE, controller_color
from ..core.view_models import ControllerState, ControllerVM


class ControllerCard(ft.Container):
    """单个动画控制器的状态与操作卡片。"""

    def __init__(
        self,
        vm: ControllerVM,
        *,
        on_toggle: Callable[[ControllerVM, bool], None],
        on_trigger: Callable[[ControllerVM], None] | None = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._on_trigger = on_trigger
        running = vm.state is ControllerState.RUNNING

        dot = ft.Container(
            width=10,
            height=10,
            border_radius=5,
            bgcolor=controller_color(vm.state),
        )
        name = ft.Text(vm.display_name, size=TYPE.body, color=PALETTE.text)

        if vm.type == "oneshot":
            action: ft.Control = ft.IconButton(
                icon=ft.Icons.PLAY_ARROW,
                icon_size=TYPE.icon,
                icon_color=PALETTE.primary_hover,
                tooltip="触发",
                on_click=lambda _e: self._on_trigger(vm) if self._on_trigger is not None else None,
            )
        else:
            action = ft.IconButton(
                icon=ft.Icons.PAUSE if running else ft.Icons.PLAY_ARROW,
                icon_size=TYPE.icon,
                icon_color=PALETTE.primary_hover,
                tooltip="停止" if running else "启动",
                on_click=lambda _e, run=running: self._on_toggle(vm, not run),
            )

        super().__init__(
            bgcolor=PALETTE.surface_alt,
            border_radius=ft.border_radius.all(8),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row([dot, name], spacing=8),
                    action,
                ],
            ),
        )
