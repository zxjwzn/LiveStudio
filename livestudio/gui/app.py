"""LiveStudio GUI 主入口。"""

from __future__ import annotations

import asyncio

import flet as ft
from livestudio.gui.app_shell import AppShell

from livestudio.app.vtubestudio.app import VTubeStudioApp
from livestudio.gui.theme import Typography
from livestudio.services.animations import AnimationManager
from livestudio.services.audio_stream import AudioStreamRouter


async def main(page: ft.Page) -> None:
    page.title = "LiveStudio"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.min_width = 1080
    page.window.min_height = 700
    page.window.width = 1180
    page.window.height = 760
    page.fonts = {"default": Typography.default_font}
    page.theme = ft.Theme(font_family="default")
    page.padding = 0

    # 1. 实例化依赖
    audio_stream = AudioStreamRouter()
    animation_manager = AnimationManager()
    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_stream,
    )

    # 2. 初始化核心系统
    await audio_stream.initialize()
    await vtubestudio_app.initialize()

    # 此处假设用户在 UI 点击启动，或者进入立即启动，按规范我们可以在此处先不 `start()`
    # 或者作为入口也可以启动服务。
    # 这里我们暂不直接启动所有服务，交由 UI 控制或在这里统一启动。
    # await audio_stream.start()
    # await vtubestudio_app.start()

    # 3. 初始化 UI Shell
    shell = AppShell(app_context=vtubestudio_app)
    page.add(shell)
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
