"""卡片、徽章与页面标题等通用 UI 组件。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft

from livestudio.gui.components.controls import icon_tile, tonal_button
from livestudio.gui.theme import Colors, Layout


@dataclass(frozen=True, slots=True)
class StatusBadge:
    """状态徽章数据。"""

    label: str
    color: str = Colors.text_secondary.hex
    background: str = Colors.surface_variant.hex

    def build(self) -> ft.Container:
        """构建状态徽章控件。"""

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=999,
            bgcolor=self.background,
            border=ft.border.all(1, Colors.border.hex),
            content=ft.Text(
                self.label,
                size=12,
                weight=ft.FontWeight.W_600,
                color=self.color,
            ),
        )


@dataclass(frozen=True, slots=True)
class MetricCard:
    """指标卡片数据。"""

    title: str
    value: str
    description: str
    icon: str
    accent: str = Colors.accent.hex

    def build(self) -> ft.Container:
        """构建指标卡片。"""

        return ft.Container(
            width=230,
            padding=Layout.padding_lg,
            border_radius=Layout.radius_lg,
            bgcolor=Colors.surface.hex,
            border=ft.border.all(1, Colors.border_subtle.hex),
            shadow=ft.BoxShadow(
                blur_radius=18,
                spread_radius=0,
                color=Colors.shadow.with_opacity(0.24),
                offset=ft.Offset(0, 6),
            ),
            content=ft.Column(
                spacing=Layout.spacing_md,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                self.title,
                                size=13,
                                color=Colors.text_secondary.hex,
                                weight=ft.FontWeight.W_600,
                            ),
                            icon_tile(self.icon, accent=self.accent),
                        ],
                    ),
                    ft.Text(
                        self.value,
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=Colors.text_primary.hex,
                    ),
                    ft.Text(
                        self.description,
                        size=12,
                        color=Colors.text_secondary.hex,
                    ),
                ],
            ),
        )


def page_title(
    title: str,
    subtitle: str,
    *,
    actions: Sequence[ft.Control] | None = None,
) -> ft.Row:
    """构建页面标题区。"""

    return ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Column(
                spacing=Layout.spacing_xs,
                controls=[
                    ft.Text(
                        title,
                        size=26,
                        weight=ft.FontWeight.BOLD,
                        color=Colors.text_primary.hex,
                    ),
                    ft.Text(subtitle, size=14, color=Colors.text_secondary.hex),
                ],
            ),
            ft.Row(spacing=Layout.spacing_sm, controls=list(actions or [])),
        ],
    )


def action_card(
    *,
    title: str,
    description: str,
    icon: str,
    button_text: str,
    on_click: Callable[[ft.ControlEvent], None] | None = None,
) -> ft.Container:
    """构建带按钮的操作卡片。"""

    return ft.Container(
        padding=Layout.padding_lg,
        border_radius=Layout.radius_lg,
        bgcolor=Colors.surface.hex,
        border=ft.border.all(1, Colors.border_subtle.hex),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    spacing=Layout.spacing_md,
                    controls=[
                        icon_tile(icon),
                        ft.Column(
                            spacing=Layout.spacing_xs,
                            controls=[
                                ft.Text(
                                    title,
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                    color=Colors.text_primary.hex,
                                ),
                                ft.Text(
                                    description,
                                    size=13,
                                    color=Colors.text_secondary.hex,
                                ),
                            ],
                        ),
                    ],
                ),
                tonal_button(button_text, on_click=on_click),
            ],
        ),
    )
