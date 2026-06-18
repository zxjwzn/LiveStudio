"""占位组件：用于尚未实现的页面区域。

P1 阶段大量页面只有骨架，统一用居中的图标 + 标题 + 副标题占位，
保证导航与主题可视化验证，后续阶段替换为真实内容。
"""

from __future__ import annotations

import flet as ft

from ..core.theme import PALETTE


class Placeholder(ft.Container):
    """居中的页面占位内容。"""

    def __init__(self, icon: str, title: str, subtitle: str = "") -> None:
        controls: list[ft.Control] = [
            ft.Icon(icon, size=64, color=PALETTE.primary),
            ft.Text(title, size=22, weight=ft.FontWeight.W_600, color=PALETTE.text),
        ]
        if subtitle:
            controls.append(ft.Text(subtitle, size=14, color=PALETTE.text_muted))

        super().__init__(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                controls=controls,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )
