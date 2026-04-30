"""页面占位区域框组件。"""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from livestudio.gui.theme import Colors, Layout


def placeholder_region(
    *,
    title: str,
    content: ft.Control,
    description: str | None = None,
    expand: bool | int | None = None,
    width: float | None = None,
    height: float | None = None,
    dense: bool = False,
    visible_frame: bool = False,
) -> ft.Container:
    """构建用于分割页面内容的占位区域框。"""

    if not visible_frame:
        return ft.Container(
            expand=expand,
            width=width,
            height=height,
            padding=Layout.padding_md if dense else Layout.padding_lg,
            content=content,
        )

    header_controls: list[ft.Control] = [
        ft.Text(
            title,
            size=15 if dense else 18,
            weight=ft.FontWeight.BOLD,
            color=Colors.text_primary.hex,
        ),
    ]
    if description is not None:
        header_controls.append(
            ft.Text(
                description,
                size=12,
                color=Colors.text_secondary.hex,
            ),
        )

    return ft.Container(
        expand=expand,
        width=width,
        height=height,
        padding=Layout.padding_md if dense else Layout.padding_lg,
        border_radius=Layout.radius_md if dense else Layout.radius_lg,
        bgcolor=Colors.surface.hex if not dense else Colors.surface_variant.hex,
        border=ft.border.all(
            1,
            Colors.border.hex if dense else Colors.border_subtle.hex,
        ),
        content=ft.Column(
            spacing=Layout.spacing_md,
            controls=[
                ft.Column(
                    spacing=Layout.spacing_xs,
                    controls=header_controls,
                ),
                ft.Divider(height=1, color=Colors.divider.hex),
                content,
            ],
        ),
    )


def placeholder_grid(
    controls: Sequence[ft.Control],
    *,
    spacing: int = Layout.spacing_lg,
) -> ft.Row:
    """构建由多个占位区域框组成的自适应网格。"""

    return ft.Row(
        wrap=True,
        spacing=spacing,
        run_spacing=spacing,
        controls=list(controls),
    )
