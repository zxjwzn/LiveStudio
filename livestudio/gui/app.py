"""图形界面的入口文件。"""

import flet as ft

from livestudio.gui.components.shell import AppShell
from livestudio.gui.pages import (
    AudioPage,
    ControllersPage,
    ExpressionPage,
    MonitorPage,
    PlatformPage,
)
from livestudio.gui.state import GUIState, PageId
from livestudio.gui.theme import Colors, Typography


async def main(page: ft.Page) -> None:
    page.title = "LiveStudio"
    page.window.width = 1100
    page.window.height = 700
    page.window.min_width = 900
    page.window.min_height = 600
    page.padding = 0
    page.spacing = 0
    page.bgcolor = Colors.background.hex
    page.fonts = {"default": Typography.default_font}
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=Colors.accent.hex,
            surface=Colors.surface.hex,
            background=Colors.background.hex,
        ),
        font_family=Typography.default_font,
    )

    state = GUIState()
    shell = AppShell(
        state,
        {
            PageId.MONITOR: MonitorPage,
            PageId.PLATFORM: PlatformPage,
            PageId.AUDIO: AudioPage,
            PageId.EXPRESSION: ExpressionPage,
            PageId.CONTROLLERS: ControllersPage,
        },
    )
    page.add(shell)


def run() -> None:
    ft.app(target=main)


if __name__ == "__main__":
    run()
