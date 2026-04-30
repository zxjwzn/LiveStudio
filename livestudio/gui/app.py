"""LiveStudio Flet GUI 应用壳。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components import HeaderBar, NavigationItem, SidebarNavigation
from livestudio.gui.pages import (
    AnimationsPage,
    AudioPage,
    DashboardPage,
    PageDefinition,
    SettingsPage,
    VTubeStudioPage,
)
from livestudio.gui.theme import Colors, Layout, Typography


class LiveStudioGuiApp:
    """LiveStudio 首版 GUI 应用壳。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._pages = self._create_pages()
        self._selected_route = self._pages[0].route
        self._body = ft.Row(expand=True, spacing=0)

    def run(self) -> None:
        """初始化并渲染 GUI。"""

        self.page.title = "LiveStudio"
        self.page.bgcolor = Colors.background.hex
        self.page.padding = 0
        self.page.spacing = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(
            color_scheme_seed=Colors.accent.hex,
            font_family=Typography.default_font_family,
            use_material3=True,
        )
        self.page.fonts = {
            Typography.default_font_family: "C:/Windows/Fonts/msyh.ttc",
            Typography.fallback_font_family: "C:/Windows/Fonts/msyh.ttc",
        }
        self.page.window.min_width = 1120
        self.page.window.min_height = 720

        self.page.add(
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    HeaderBar(
                        running=False,
                        message="GUI 已就绪，服务尚未启动",
                    ).build(),
                    self._body,
                ],
            ),
        )
        self._render_body()

    def _create_pages(self) -> list[PageDefinition]:
        page_views = [
            DashboardPage(),
            VTubeStudioPage(),
            AudioPage(),
            AnimationsPage(),
            SettingsPage(),
        ]
        return [
            PageDefinition(
                route=view.route,
                title=view.title,
                description=view.description,
                icon=view.icon,
                view=view,
            )
            for view in page_views
        ]

    def _render_body(self) -> None:
        selected_page = self._get_selected_page()
        navigation_items = [
            NavigationItem(
                route=page.route,
                title=page.title,
                description=page.description,
                icon=page.icon,
            )
            for page in self._pages
        ]
        self._body.controls = [
            SidebarNavigation(
                items=navigation_items,
                selected_route=self._selected_route,
                on_select=self._select_page,
            ).build(),
            ft.Container(
                expand=True,
                padding=Layout.padding_xl,
                bgcolor=Colors.background.hex,
                content=selected_page.view.build(),
            ),
        ]
        self.page.update()

    def _select_page(self, route: str) -> None:
        if route == self._selected_route:
            return
        self._selected_route = route
        self._render_body()

    def _get_selected_page(self) -> PageDefinition:
        for page in self._pages:
            if page.route == self._selected_route:
                return page
        return self._pages[0]


def main(page: ft.Page) -> None:
    """Flet 入口。"""

    LiveStudioGuiApp(page).run()


if __name__ == "__main__":
    ft.app(target=main)
