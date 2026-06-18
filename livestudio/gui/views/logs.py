"""日志页。

P1 已接通 AppState.logs 的渲染（订阅 ObservableList 即时刷新）；
日志来源（loguru sink）在 P2 的 LogController 接入。
"""

from __future__ import annotations

import flet as ft

from ..core.base_view import BaseView
from ..core.theme import PALETTE, level_color
from ..core.view_models import LogEntryVM


class LogsView(BaseView):
    """日志视图：订阅 AppState.logs 实时渲染。"""

    def build_content(self) -> ft.Control:
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
            [
                ft.Text("日志", size=22, weight=ft.FontWeight.W_600, color=PALETTE.text),
                self._body,
            ],
            spacing=14,
            expand=True,
        )

    def bind(self) -> None:
        self.watch(self.state.logs, self._on_logs)

    def _on_logs(self, entries: list[LogEntryVM]) -> None:
        if not entries:
            self._body.content = self._empty
            self.safe_update()
            return
        self._list.controls = [self._row(entry) for entry in entries]
        self._body.content = self._list
        self.safe_update()

    def _row(self, entry: LogEntryVM) -> ft.Control:
        return ft.Row(
            [
                ft.Text(entry.ts, size=12, color=PALETTE.text_muted, font_family="monospace"),
                ft.Text(entry.level, size=12, weight=ft.FontWeight.W_600, color=level_color(entry.level), width=64),
                ft.Text(entry.message, size=12, color=PALETTE.text, expand=True, selectable=True),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
