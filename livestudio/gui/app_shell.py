"""UI 应用壳容器，负责主框架、侧边导航与页面切换。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft
from livestudio.gui.views.animation_view import AnimationView
from livestudio.gui.views.audio_view import AudioView
from livestudio.gui.views.overview_view import OverviewView
from livestudio.gui.views.settings_view import SettingsView
from livestudio.gui.views.vtube_studio_view import VTubeStudioView

from livestudio.gui.theme import Colors, Layout

if TYPE_CHECKING:
    from livestudio.app.vtubestudio.app import VTubeStudioApp


class AppShell(ft.Container):
    """主界面壳容器，管理 NavigationRail 和多视图切换。"""

    def __init__(self, app_context: VTubeStudioApp) -> None:
        super().__init__(expand=True)
        self.app_context = app_context

        self.overview_view = OverviewView(app_context)
        self.vtube_studio_view = VTubeStudioView(app_context)
        self.animation_view = AnimationView(app_context)
        self.audio_view = AudioView(app_context)
        self.settings_view = SettingsView(app_context)

        self._views = [
            self.overview_view,
            self.vtube_studio_view,
            self.animation_view,
            self.audio_view,
            self.settings_view,
        ]

        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=150,
            group_alignment=-0.9,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DASHBOARD_OUTLINED,
                    selected_icon=ft.Icons.DASHBOARD,
                    label="总览",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.VIDEOGAME_ASSET_OUTLINED,
                    selected_icon=ft.Icons.VIDEOGAME_ASSET,
                    label="VTS",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.ANIMATION_OUTLINED,
                    selected_icon=ft.Icons.ANIMATION,
                    label="动画",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.AUDIO_FILE_OUTLINED,
                    selected_icon=ft.Icons.AUDIO_FILE,
                    label="音频",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="设置",
                ),
            ],
            on_change=self.on_nav_change,
            bgcolor=Colors.surface.hex,
            indicator_color=Colors.surface_variant.hex,
            selected_label_text_style=ft.TextStyle(
                color=Colors.accent.hex,
                weight=ft.FontWeight.BOLD,
            ),
        )

        self.content_container = ft.Container(
            content=self.overview_view,
            expand=True,
            bgcolor=Colors.background.hex,
            padding=Layout.padding_lg,
        )

        self.content = ft.Row(
            controls=[
                self.rail,
                ft.VerticalDivider(width=1),
                self.content_container,
            ],
            expand=True,
            spacing=0,
        )

    def on_nav_change(self, e: ft.ControlEvent) -> None:
        """处理导航栏切换。"""
        selected_index = e.control.selected_index
        if 0 <= selected_index < len(self._views):
            self.content_container.content = self._views[selected_index]
            self.content_container.update()
