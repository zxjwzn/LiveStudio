"""日志页（P5 完善）。

订阅 ``state.logs``，提供:
- 级别下拉过滤（ALL / TRACE / DEBUG / INFO / SUCCESS / WARNING / ERROR / CRITICAL）
- 关键字过滤（仅匹配 message，本地筛选不回写状态）
- 暂停（仅停止 UI 追加，缓冲继续）
- 清空（仅清当前视图列表，不动 state.logs）
- 自动滚动开关
"""

from __future__ import annotations

import flet as ft

from ..core.base_view import BaseView
from ..core.theme import PALETTE, level_color
from ..core.view_models import LogEntryVM

_LEVELS: tuple[str, ...] = ("ALL", "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")
_LEVEL_PRIORITY: dict[str, int] = {name: i for i, name in enumerate(_LEVELS)}


class LogsView(BaseView):
    """日志视图：订阅 AppState.logs 实时渲染 + 本地过滤/暂停/清空。"""

    def build_content(self) -> ft.Control:
        # —— 视图本地状态（不回写 AppState）——
        self._level_filter: str = "ALL"
        self._keyword: str = ""
        self._paused: bool = False
        self._auto_scroll: bool = True

        # —— 工具栏控件 ——
        self._level_dropdown = ft.Dropdown(
            label="级别",
            value="ALL",
            width=140,
            on_change=self._on_level_change,
            options=[ft.dropdown.Option(level) for level in _LEVELS],
        )
        self._keyword_field = ft.TextField(
            label="过滤关键字",
            hint_text="按消息内容过滤",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_keyword_change,
            expand=True,
            dense=True,
        )
        self._pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE,
            icon_color=PALETTE.primary_hover,
            tooltip="暂停",
            on_click=self._on_pause_click,
        )
        self._clear_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=PALETTE.text_muted,
            tooltip="清空当前视图（不动状态缓冲）",
            on_click=self._on_clear_click,
        )
        self._auto_scroll_switch = ft.Switch(
            label="自动滚动",
            value=True,
            on_change=self._on_auto_scroll_change,
            active_color=PALETTE.primary,
        )

        toolbar = ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self._level_dropdown,
                self._keyword_field,
                self._pause_button,
                self._clear_button,
                self._auto_scroll_switch,
            ],
        )

        # —— 日志列表 ——
        self._list = ft.ListView(expand=True, spacing=2, auto_scroll=True, padding=12)
        self._empty = ft.Container(
            content=ft.Text("暂无日志", color=PALETTE.text_muted, size=13),
            alignment=ft.alignment.center,
            expand=True,
        )
        self._body = ft.Container(
            content=self._empty,
            expand=True,
            bgcolor=PALETTE.surface,
            border=ft.border.all(1, PALETTE.border),
            border_radius=ft.border_radius.all(12),
        )

        return ft.Column(
            expand=True,
            spacing=14,
            controls=[
                ft.Text("日志", size=22, weight=ft.FontWeight.W_600, color=PALETTE.text),
                toolbar,
                self._body,
            ],
        )

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.logs, self._on_logs)

    def _on_logs(self, entries: list[LogEntryVM]) -> None:
        if self._paused:
            return
        self._render(entries)

    def _render(self, entries: list[LogEntryVM]) -> None:
        filtered = [entry for entry in entries if self._matches(entry)]
        if not filtered:
            self._body.content = self._empty
            self.safe_update()
            return
        self._list.controls = [self._row(entry) for entry in filtered]
        self._list.auto_scroll = self._auto_scroll
        self._body.content = self._list
        self.safe_update()

    # —— 过滤逻辑 ——
    def _matches(self, entry: LogEntryVM) -> bool:
        if self._level_filter != "ALL":
            min_prio = _LEVEL_PRIORITY.get(self._level_filter, 0)
            entry_prio = _LEVEL_PRIORITY.get(entry.level.upper(), 0)
            if entry_prio < min_prio:
                return False
        return not (self._keyword and self._keyword.lower() not in entry.message.lower())

    # —— 工具栏回调 ——
    def _on_level_change(self, e: ft.ControlEvent) -> None:
        self._level_filter = e.control.value or "ALL"
        self._render(self.state.logs.value)

    def _on_keyword_change(self, e: ft.ControlEvent) -> None:
        self._keyword = (e.control.value or "").strip()
        self._render(self.state.logs.value)

    def _on_pause_click(self, _e: ft.ControlEvent) -> None:
        self._paused = not self._paused
        if self._paused:
            self._pause_button.icon = ft.Icons.PLAY_ARROW
            self._pause_button.tooltip = "继续"
        else:
            self._pause_button.icon = ft.Icons.PAUSE
            self._pause_button.tooltip = "暂停"
            # 继续时立即拉一次最新
            self._render(self.state.logs.value)
        self.safe_update()

    def _on_clear_click(self, _e: ft.ControlEvent) -> None:
        # 仅清空当前视图；state.logs 缓冲不动，新日志会继续追加
        self._list.controls = []
        self._body.content = self._empty
        self.safe_update()

    def _on_auto_scroll_change(self, e: ft.ControlEvent) -> None:
        self._auto_scroll = bool(e.control.value)
        self._list.auto_scroll = self._auto_scroll
        self.safe_update()

    # —— 行渲染 ——
    def _row(self, entry: LogEntryVM) -> ft.Control:
        return ft.Row(
            [
                ft.Text(entry.ts, size=12, color=PALETTE.text_muted, font_family="monospace"),
                ft.Text(entry.level, size=12, weight=ft.FontWeight.W_600, color=level_color(entry.level), width=72),
                ft.Text(entry.message, size=12, color=PALETTE.text, expand=True, selectable=True),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
