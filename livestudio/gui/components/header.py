"""顶部标题与运行状态栏。"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from livestudio.gui.components.cards import StatusBadge
from livestudio.gui.components.controls import primary_button, secondary_button
from livestudio.gui.theme import Colors, Layout


@dataclass(frozen=True, slots=True)
class HeaderBar:
    """应用顶部状态栏。"""

    running: bool = False
    message: str = "待启动"

    def build(self) -> ft.Container:
        """构建顶部状态栏。"""

        status_badge = StatusBadge(
            label="运行中" if self.running else "未启动",
            color=Colors.success.hex if self.running else Colors.warning.hex,
            background=Colors.success.with_opacity(0.12)
            if self.running
            else Colors.warning.with_opacity(0.14),
        )
        return ft.Container(
            height=76,
            padding=ft.padding.symmetric(horizontal=Layout.padding_xl, vertical=12),
            bgcolor=Colors.surface.hex,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.divider.hex)),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=Layout.spacing_md,
                        controls=[
                            ft.Container(
                                width=44,
                                height=44,
                                border_radius=Layout.radius_lg,
                                bgcolor=Colors.accent.hex,
                                alignment=ft.alignment.center,
                                content=ft.Icon(
                                    ft.Icons.AUTO_AWESOME,
                                    color=Colors.text_on_accent.hex,
                                ),
                            ),
                            ft.Column(
                                spacing=2,
                                alignment=ft.MainAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        "LiveStudio",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                        color=Colors.text_primary.hex,
                                    ),
                                    ft.Text(
                                        "VTube Studio 直播控制台",
                                        size=13,
                                        color=Colors.text_secondary.hex,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=Layout.spacing_md,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            status_badge.build(),
                            ft.Text(
                                self.message,
                                size=13,
                                color=Colors.text_secondary.hex,
                            ),
                            secondary_button(
                                "刷新状态",
                                icon=ft.Icons.REFRESH,
                            ),
                            primary_button(
                                "启动服务" if not self.running else "停止服务",
                                icon=ft.Icons.PLAY_ARROW
                                if not self.running
                                else ft.Icons.STOP,
                            ),
                        ],
                    ),
                ],
            ),
        )
