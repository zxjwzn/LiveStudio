"""一些常用的小界面组件。"""

import flet as ft

from livestudio.gui.theme import Colors, Layout


def page_title(text: str, subtitle: str | None = None) -> ft.Column:
    controls: list[ft.Control] = [
        ft.Text(text, size=28, weight=ft.FontWeight.BOLD, color=Colors.text_primary.hex),
    ]
    if subtitle:
        controls.append(ft.Text(subtitle, size=13, color=Colors.text_secondary.hex))
    return ft.Column(controls, spacing=Layout.spacing_xs)


def card(title: str, controls: list[ft.Control]) -> ft.Container:
    return ft.Container(
        bgcolor=Colors.surface.hex,
        border=ft.border.all(1, Colors.border.hex),
        border_radius=Layout.radius_lg,
        padding=Layout.padding_lg,
        content=ft.Column(
            [
                ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=Colors.text_primary.hex),
                *controls,
            ],
            spacing=Layout.spacing_md,
        ),
    )


def page_body(*controls: ft.Control) -> ft.Container:
    return ft.Container(
        expand=True,
        padding=Layout.padding_xl,
        content=ft.Column(list(controls), spacing=Layout.spacing_lg, scroll=ft.ScrollMode.AUTO),
    )


def placeholder_page(title: str, subtitle: str, note: str) -> ft.Container:
    return page_body(
        page_title(title, subtitle),
        card("开发占位", [ft.Text(note, color=Colors.text_secondary.hex)]),
    )
