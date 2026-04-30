"""统一样式的基础 GUI 控件封装。"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import flet as ft

from livestudio.gui.theme import Colors, Layout

ControlEventHandler = Callable[[ft.ControlEvent], None] | None


def primary_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: ControlEventHandler = None,
) -> ft.FilledButton:
    """构建主操作按钮。"""

    return ft.FilledButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=Colors.accent.hex,
            color=Colors.text_on_accent.hex,
            shape=ft.RoundedRectangleBorder(radius=Layout.radius_md),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def secondary_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: ControlEventHandler = None,
) -> ft.OutlinedButton:
    """构建次级描边按钮。"""

    return ft.OutlinedButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=Colors.accent.hex,
            side=ft.BorderSide(1, Colors.border_accent.hex),
            shape=ft.RoundedRectangleBorder(radius=Layout.radius_md),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def tonal_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: ControlEventHandler = None,
) -> ft.FilledTonalButton:
    """构建浅色强调按钮。"""

    return ft.FilledTonalButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=Colors.pink_lightest.hex,
            color=Colors.accent.hex,
            shape=ft.RoundedRectangleBorder(radius=Layout.radius_md),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
        ),
    )


def styled_switch(
    *,
    label: str | None = None,
    value: bool = False,
    on_change: ControlEventHandler = None,
) -> ft.Switch:
    """构建统一颜色的开关。"""

    return ft.Switch(
        label=label,
        value=value,
        active_color=Colors.toggle_thumb.hex,
        active_track_color=Colors.toggle_track_on.hex,
        inactive_thumb_color=Colors.toggle_thumb.hex,
        inactive_track_color=Colors.toggle_track_off.hex,
        on_change=on_change,
    )


def styled_dropdown(
    *,
    label: str,
    value: str | None = None,
    options: Sequence[ft.DropdownOption],
    width: float | None = None,
    on_change: ControlEventHandler = None,
) -> ft.Dropdown:
    """构建统一样式的下拉框。"""

    return ft.Dropdown(
        label=label,
        value=value,
        width=width,
        options=list(options),
        bgcolor=Colors.dropdown_background.hex,
        border_color=Colors.input_border.hex,
        focused_border_color=Colors.input_border_focus.hex,
        border_radius=Layout.radius_md,
        color=Colors.text_primary.hex,
        on_change=on_change,
    )


def styled_text_field(
    *,
    label: str,
    value: str = "",
    read_only: bool = False,
    width: float | None = None,
    on_change: ControlEventHandler = None,
) -> ft.TextField:
    """构建统一样式的文本输入框。"""

    return ft.TextField(
        label=label,
        value=value,
        read_only=read_only,
        width=width,
        bgcolor=Colors.input_background.hex,
        border_color=Colors.input_border.hex,
        focused_border_color=Colors.input_border_focus.hex,
        border_radius=Layout.radius_md,
        color=Colors.text_primary.hex,
        on_change=on_change,
    )


def styled_progress_bar(
    *,
    value: float | None = None,
    expand: bool | int | None = None,
) -> ft.ProgressBar:
    """构建统一样式的进度条。"""

    return ft.ProgressBar(
        expand=expand,
        value=value,
        color=Colors.slider_track_active.hex,
        bgcolor=Colors.slider_track.hex,
    )


def icon_tile(icon: str, *, accent: str = Colors.accent.hex) -> ft.Container:
    """构建统一样式的图标块。"""

    return ft.Container(
        width=42,
        height=42,
        border_radius=Layout.radius_md,
        bgcolor=Colors.pink_lightest.hex,
        alignment=ft.alignment.center,
        content=ft.Icon(icon, color=accent),
    )
