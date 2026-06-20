"""AppShell：应用外壳。

左侧 NavigationRail（5 个一级入口）+ 顶部状态栏 + 右侧内容容器。
内容区按路由懒加载并缓存视图实例；切换时旧视图随控件树移除自动触发
will_unmount 退订，新视图 did_mount 重新订阅。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from ..components.toaster import ErrorToaster
from ..core.theme import PALETTE, TYPE, connection_color
from ..core.view_context import ViewContext
from ..core.view_models import AudioLevelVM, PlatformStatusVM, audio_source_label
from .audio import AudioView
from .dashboard import DashboardView
from .logs import LogsView
from .platform import PlatformView
from .settings import SettingsView


@dataclass(frozen=True)
class NavItem:
    """侧边栏一级入口定义。"""

    route: str
    label: str
    icon: str
    selected_icon: str
    factory: Callable[[ViewContext], ft.Control]


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("dashboard", "仪表盘", ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD, DashboardView),
    NavItem("platform", "平台", ft.Icons.HUB_OUTLINED, ft.Icons.HUB, PlatformView),
    NavItem("audio", "音频流", ft.Icons.GRAPHIC_EQ, ft.Icons.GRAPHIC_EQ, AudioView),
    NavItem("logs", "日志", ft.Icons.ARTICLE_OUTLINED, ft.Icons.ARTICLE, LogsView),
    NavItem("settings", "设置", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, SettingsView),
)


class AppShell(ft.Row):
    """应用外壳：导航 + 状态栏 + 内容容器。"""

    def __init__(self, ctx: ViewContext) -> None:
        super().__init__(expand=True, spacing=0)
        self.ctx = ctx
        self.ctx.navigate = self.navigate  # 装配路由跳转，替换默认 no-op
        self._views: dict[str, ft.Control] = {}  # 路由 -> 视图实例缓存
        self._route_index = {item.route: i for i, item in enumerate(NAV_ITEMS)}
        self._toaster: ErrorToaster | None = None  # did_mount 时 page 就绪才建立

        self._rail = self._build_rail()
        self._content = ft.Container(expand=True, padding=20)
        self._topbar = self._build_topbar()

        right = ft.Column(
            [self._topbar, ft.Divider(height=1, color=PALETTE.border), self._content],
            spacing=0,
            expand=True,
        )
        self.controls = [
            self._rail,
            ft.VerticalDivider(width=1, color=PALETTE.border),
            right,
        ]
        self.navigate(NAV_ITEMS[0].route)

    # —— 导航栏 ——
    def _build_rail(self) -> ft.NavigationRail:
        return ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=88,
            bgcolor=PALETTE.surface,
            indicator_color=PALETTE.primary_soft,
            leading=ft.Container(
                content=ft.Text("🌸", size=TYPE.title),
                padding=ft.padding.symmetric(vertical=16),
                tooltip="LiveStudio",
            ),
            group_alignment=-0.9,
            destinations=[
                ft.NavigationRailDestination(
                    icon=item.icon,
                    selected_icon=item.selected_icon,
                    label=item.label,
                )
                for item in NAV_ITEMS
            ],
            on_change=self._on_rail_change,
        )

    def _on_rail_change(self, e: ft.ControlEvent) -> None:
        self.navigate(NAV_ITEMS[e.control.selected_index].route)

    # —— 顶部状态栏 ——
    def _build_topbar(self) -> ft.Control:
        self._status_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=PALETTE.text_muted)
        self._status_text = ft.Text("未连接", size=TYPE.body, color=PALETTE.text_muted)
        self._audio_text = ft.Text("音频未启动", size=TYPE.body, color=PALETTE.text_muted)
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=14),
            bgcolor=PALETTE.surface,
            content=ft.Row(
                [
                    ft.Text("LiveStudio", size=TYPE.heading, weight=ft.FontWeight.W_600, color=PALETTE.primary_hover),
                    ft.Row(
                        [
                            ft.Row([self._status_dot, self._status_text], spacing=6),
                            ft.Container(width=16),
                            ft.Icon(ft.Icons.MULTITRACK_AUDIO, size=TYPE.heading, color=PALETTE.text_muted),
                            self._audio_text,
                        ],
                        spacing=6,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    # —— 路由切换 ——
    def navigate(self, route: str) -> None:
        if route not in self._route_index:
            return
        view = self._views.get(route)
        if view is None:
            item = NAV_ITEMS[self._route_index[route]]
            view = item.factory(self.ctx)
            self._views[route] = view
        self._content.content = view
        self._rail.selected_index = self._route_index[route]
        if self.page is not None:
            self.page.update()

    # —— 顶栏状态订阅（随 Shell 挂载建立）——
    def did_mount(self) -> None:
        self._unsub_platform = self.ctx.state.platforms.subscribe(self._on_platforms)
        self._unsub_active = self.ctx.state.active_platform_id.subscribe(lambda _: self._on_platforms(None))
        self._unsub_audio = self.ctx.state.audio_level.subscribe(self._on_audio)
        # 全局错误/警告浮层：page 挂载后才可 open SnackBar，故在此建立。
        # did_mount 时 page 通常已就绪；用显式守卫而非 assert，避免 -O 下被剥掉。
        if self.page is not None:
            self._toaster = ErrorToaster(self.page, self.ctx.state.logs)
            self._toaster.start()

    def will_unmount(self) -> None:
        for unsub in (self._unsub_platform, self._unsub_active, self._unsub_audio):
            unsub()
        if self._toaster is not None:
            self._toaster.stop()

    def _on_platforms(self, _value: object) -> None:
        status: PlatformStatusVM | None = self.ctx.state.active_platform_status()
        if status is None and self.ctx.state.platforms.value:
            status = self.ctx.state.platforms.value[0]
        if status is None:
            self._status_dot.bgcolor = PALETTE.text_muted
            self._status_text.value = "未连接"
            self._status_text.color = PALETTE.text_muted
        else:
            color = connection_color(status.connection)
            self._status_dot.bgcolor = color
            label = status.display_name
            if status.model_name:
                label += f" · {status.model_name}"
            self._status_text.value = label
            self._status_text.color = PALETTE.text
        self._safe_update()

    def _on_audio(self, level: AudioLevelVM) -> None:
        if level.active:
            self._audio_text.value = audio_source_label(level.source)
            self._audio_text.color = PALETTE.text
        else:
            self._audio_text.value = "音频未启动"
            self._audio_text.color = PALETTE.text_muted
        self._safe_update()

    def _safe_update(self) -> None:
        if self.page is not None:
            self.update()
