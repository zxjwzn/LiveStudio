"""左侧常驻页面导航栏。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft

from livestudio.gui.theme import Colors, Layout


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """页面导航项。"""

    route: str
    title: str
    description: str
    icon: str


class SidebarNavigation:
    """常驻页面导航栏。"""

    def __init__(
        self,
        *,
        items: Sequence[NavigationItem],
        selected_route: str,
        on_select: Callable[[str], None],
    ) -> None:
        self.items = list(items)
        self.selected_route = selected_route
        self.on_select = on_select

    def build(self) -> ft.Container:
        """构建导航栏。"""

        return ft.Container(
            width=260,
            padding=Layout.padding_lg,
            bgcolor=Colors.surface.hex,
            border=ft.border.only(right=ft.BorderSide(1, Colors.divider.hex)),
            content=ft.Column(
                expand=True,
                spacing=Layout.spacing_md,
                controls=[
                    ft.Text(
                        "页面导航",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=Colors.text_secondary.hex,
                    ),
                    *[self._build_item(item) for item in self.items],
                    ft.Container(expand=True),
                    ft.Container(
                        padding=Layout.padding_md,
                        border_radius=Layout.radius_lg,
                        bgcolor=Colors.surface_variant.hex,
                        border=ft.border.all(1, Colors.border.hex),
                        content=ft.Column(
                            spacing=Layout.spacing_xs,
                            controls=[
                                ft.Text(
                                    "首版 UI 骨架",
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color=Colors.text_primary.hex,
                                ),
                                ft.Text(
                                    "页面已按文件拆分，可逐页接入真实服务状态。",
                                    size=12,
                                    color=Colors.text_secondary.hex,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _build_item(self, item: NavigationItem) -> ft.Container:
        selected = item.route == self.selected_route
        return ft.Container(
            padding=Layout.padding_md,
            border_radius=Layout.radius_lg,
            bgcolor=Colors.pink_lightest.hex if selected else Colors.surface.hex,
            border=ft.border.all(
                1,
                Colors.border_accent.hex if selected else Colors.border_subtle.hex,
            ),
            ink=True,
            on_click=lambda _: self.on_select(item.route),
            content=ft.Row(
                spacing=Layout.spacing_md,
                controls=[
                    ft.Container(
                        width=38,
                        height=38,
                        border_radius=Layout.radius_md,
                        bgcolor=Colors.accent.hex
                        if selected
                        else Colors.surface_variant.hex,
                        alignment=ft.alignment.center,
                        content=ft.Icon(
                            item.icon,
                            size=20,
                            color=Colors.text_on_accent.hex
                            if selected
                            else Colors.accent.hex,
                        ),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(
                                item.title,
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=Colors.text_primary.hex,
                            ),
                            ft.Text(
                                item.description,
                                size=11,
                                color=Colors.text_secondary.hex,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                    ),
                ],
            ),
        )
