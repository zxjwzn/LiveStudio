"""错误/警告浮层提示（非阻塞 SnackBar）。

订阅 ``AppState.logs``，对新增的 WARNING/ERROR/CRITICAL 级别日志以 SnackBar
形式弹出。SnackBar 是 Flet 的非阻塞底部浮层，自动消失，不拦截页面交互，
因此满足"以弹窗展示且不阻塞当前页面"的要求。

线程：``state.logs`` 仅由 ``LogController._drain_loop``（事件循环内的 asyncio
task）经 ``_flush`` 写入，故本订阅回调天然在 Flet 事件循环线程执行，可直接
``page.open``，无需再经 ``AsyncBridge`` marshal。

防刷屏：一次 logs 更新（默认 100ms 批量 flush 一次）内的多条告警合并为一个
SnackBar（显示最新一条 + 累计条数），把"一条日志一个弹窗"降为"一个刷新
周期一个弹窗"；重连失败这类周期性告警因此每周期至多一个提示，而非逐条刷屏。
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ..core.observable import ObservableList
from ..core.theme import PALETTE, TYPE
from ..core.view_models import LogEntryVM

# 触发弹窗的级别；其中 _SEVERE 用红色（danger），其余告警用橙色（warning）
_ALERT_LEVELS: frozenset[str] = frozenset({"WARNING", "ERROR", "CRITICAL"})
_SEVERE_LEVELS: frozenset[str] = frozenset({"ERROR", "CRITICAL"})
_SNACKBAR_DURATION_MS = 4000


class ErrorToaster:
    """把 WARNING/ERROR/CRITICAL 日志弹成非阻塞 SnackBar。

    生命周期由持有者（AppShell）驱动：``start`` 建立订阅，``stop`` 退订。
    """

    def __init__(self, page: ft.Page, logs: ObservableList[LogEntryVM]) -> None:
        self._page = page
        self._logs = logs
        # 清空锚点：记录上次处理过的最后一条（identity）。只对其之后的新日志弹窗，
        # 避免订阅时回放历史告警，以及新日志触发全量回调时重复弹旧告警。
        self._anchor: LogEntryVM | None = None
        self._unsub: Callable[[], None] | None = None

    def start(self) -> None:
        """建立订阅。初始锚点设为当前末尾，只对订阅之后的新告警弹窗。"""

        entries = self._logs.value
        self._anchor = entries[-1] if entries else None
        self._unsub = self._logs.subscribe(self._on_logs, immediate=False)

    def stop(self) -> None:
        """退订。"""

        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def _on_logs(self, entries: list[LogEntryVM]) -> None:
        new_entries = self._after_anchor(entries)
        if entries:
            self._anchor = entries[-1]
        alerts = [entry for entry in new_entries if entry.level.upper() in _ALERT_LEVELS]
        if alerts:
            self._show(alerts)

    def _after_anchor(self, entries: list[LogEntryVM]) -> list[LogEntryVM]:
        """返回锚点之后的日志；锚点已被环形缓冲丢弃则全部视为新。"""

        anchor = self._anchor
        if anchor is None:
            return entries
        for index, entry in enumerate(entries):
            if entry is anchor:
                return entries[index + 1 :]
        return entries

    def _show(self, alerts: list[LogEntryVM]) -> None:
        """把一批告警合并成一个 SnackBar 弹出。"""

        latest = alerts[-1]
        text = f"[{latest.level}] {latest.message}"
        if len(alerts) > 1:
            text += f"  (+{len(alerts) - 1} 条)"
        severe = any(entry.level.upper() in _SEVERE_LEVELS for entry in alerts)
        snackbar = ft.SnackBar(
            content=ft.Text(text, color=PALETTE.on_primary, size=TYPE.body),
            bgcolor=PALETTE.danger if severe else PALETTE.warning,
            duration=_SNACKBAR_DURATION_MS,
            behavior=ft.SnackBarBehavior.FLOATING,
            show_close_icon=True,
            close_icon_color=PALETTE.on_primary,
        )
        self._page.open(snackbar)
