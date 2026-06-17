"""主界面外壳：左侧菜单、右侧页面、底部状态栏。"""

from collections.abc import Callable

import flet as ft

from livestudio.gui.state import GUIState, PageId
from livestudio.gui.theme import Colors, Layout

PageFactory = Callable[[GUIState], ft.Control]


NAV_ITEMS: tuple[tuple[PageId, str, str], ...] = (
    (PageId.MONITOR, ft.Icons.INSERT_CHART_OUTLINED, "监控"),
    (PageId.PLATFORM, ft.Icons.CABLE_OUTLINED, "平台"),
    (PageId.AUDIO, ft.Icons.GRAPHIC_EQ_OUTLINED, "音频"),
    (PageId.EXPRESSION, ft.Icons.THEATER_COMEDY_OUTLINED, "表情"),
    (PageId.CONTROLLERS, ft.Icons.TUNE_OUTLINED, "控制器"),
)


class AppShell(ft.Column):
    """整个窗口的主体。

    页面只创建一次。切换页面时只是显示一个、隐藏其它，
    这样输入框、下拉框、滑块的值不会因为切换页面而丢失。
    """

    def __init__(self, state: GUIState, factories: dict[PageId, PageFactory]) -> None:
        super().__init__(expand=True, spacing=0)
        self.state = state
        self.factories = factories
        self.nav_buttons: dict[PageId, ft.Container] = {}
        self.pages = {page_id: factory(state) for page_id, factory in factories.items()}
        self.stack = ft.Stack(list(self.pages.values()), expand=True)
        self.status_text = ft.Text(size=12, color=Colors.text_secondary.hex)
        self.controls = [
            ft.Row(
                [self._build_nav(), ft.Container(self.stack, expand=True)],
                expand=True,
                spacing=0,
            ),
            self._build_status_bar(),
        ]
        self.switch_page(state.current_page, update=False)

    def _build_nav(self) -> ft.Container:
        return ft.Container(
            width=80,
            bgcolor=Colors.surface.hex,
            border=ft.border.only(right=ft.BorderSide(1, Colors.border.hex)),
            padding=ft.padding.symmetric(horizontal=8, vertical=Layout.spacing_lg),
            content=ft.Column(
                [self._nav_button(page_id, icon, label) for page_id, icon, label in NAV_ITEMS],
                spacing=Layout.spacing_md,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _nav_button(self, page_id: PageId, icon: str, label: str) -> ft.Container:
        button = ft.Container(
            width=64,
            height=70,
            border_radius=Layout.radius_md,
            padding=ft.padding.symmetric(vertical=Layout.spacing_sm),
            content=ft.Column(
                [
                    ft.Icon(icon, color=Colors.accent.hex, size=24),
                    ft.Text(label, color=Colors.text_primary.hex, size=12, text_align=ft.TextAlign.CENTER),
                ],
                spacing=Layout.spacing_xs,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=lambda _event, target=page_id: self.switch_page(target),
        )
        self.nav_buttons[page_id] = button
        return button

    def _build_status_bar(self) -> ft.Container:
        return ft.Container(
            height=34,
            bgcolor=Colors.surface.hex,
            border=ft.border.only(top=ft.BorderSide(1, Colors.border.hex)),
            padding=ft.padding.symmetric(horizontal=Layout.padding_lg, vertical=8),
            content=self.status_text,
        )

    def switch_page(self, page_id: PageId, *, update: bool = True) -> None:
        self.state.current_page = page_id
        for item_page_id, control in self.pages.items():
            control.visible = item_page_id == page_id
        for item_page_id, button in self.nav_buttons.items():
            selected = item_page_id == page_id
            button.bgcolor = Colors.pink_lightest.hex if selected else None
            button.border = ft.border.all(1, Colors.border_accent.hex if selected else Colors.border_subtle.hex)
        self.status_text.value = f"状态: {self.state.status_message} | 页面: {page_id.value}"
        if update:
            self.update()
