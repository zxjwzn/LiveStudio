"""统一标题分区容器。

页面内的一块带标题的内容区域，统一卡片外观（圆角、表面色、描边）。
其它组件与页面复用它来保持视觉一致。
"""

from __future__ import annotations

import flet as ft

from ..core.theme import PALETTE


class Section(ft.Container):
    """带标题的分区卡片。"""

    def __init__(
        self,
        title: str,
        body: ft.Control,
        *,
        trailing: ft.Control | None = None,
        expand: bool | int = False,
    ) -> None:
        header_row = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=PALETTE.text),
                trailing or ft.Container(),
            ],
        )
        super().__init__(
            expand=expand,
            bgcolor=PALETTE.surface,
            border=ft.border.all(1, PALETTE.border),
            border_radius=ft.border_radius.all(12),
            padding=ft.padding.all(16),
            content=ft.Column(
                spacing=12,
                controls=[header_row, ft.Divider(height=1, color=PALETTE.border), body],
            ),
        )
