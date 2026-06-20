"""测试 ErrorToaster：WARNING/ERROR/CRITICAL 日志弹非阻塞 SnackBar。

覆盖：
- 告警级别弹 SnackBar；INFO/DEBUG 等不弹
- 订阅前的历史日志不回放（只对订阅之后的新告警弹）
- 一次 flush 内多条告警合并为一个 SnackBar（防刷屏）
- ERROR/CRITICAL 用 danger 底色，纯 WARNING 用 warning 底色
- stop 退订后不再弹

注：用假 page 捕获 open(SnackBar) 调用，不接真实 Flet。
"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components.toaster import ErrorToaster
from livestudio.gui.core.observable import ObservableList
from livestudio.gui.core.theme import PALETTE
from livestudio.gui.core.view_models import LogEntryVM


class _FakePage:
    """假 page：捕获 open 的 SnackBar。"""

    def __init__(self) -> None:
        self.opened: list[ft.SnackBar] = []

    def open(self, control: ft.SnackBar) -> None:
        self.opened.append(control)


def _log(level: str, message: str = "msg") -> LogEntryVM:
    return LogEntryVM(ts="00:00:00.000", level=level, message=message, color="#000")


def _snackbar_text(snackbar: ft.SnackBar) -> str:
    """取 SnackBar 文本内容（content 静态类型是 Control，运行时是 ft.Text）。"""

    from typing import cast

    return cast(ft.Text, snackbar.content).value or ""


def _make() -> tuple[_FakePage, ObservableList[LogEntryVM], ErrorToaster]:
    page = _FakePage()
    logs: ObservableList[LogEntryVM] = ObservableList([])
    from typing import Any, cast

    toaster = ErrorToaster(cast(Any, page), logs)
    toaster.start()
    return page, logs, toaster


def test_warning_level_pops_snackbar() -> None:
    """WARNING 触发一个 SnackBar"""
    page, logs, _ = _make()
    logs.append(_log("WARNING", "出问题了"))
    assert len(page.opened) == 1
    assert "出问题了" in _snackbar_text(page.opened[0])


def test_info_level_does_not_pop() -> None:
    """INFO/DEBUG 等不触发弹窗"""
    page, logs, _ = _make()
    logs.append(_log("INFO"))
    logs.append(_log("DEBUG"))
    logs.append(_log("SUCCESS"))
    assert page.opened == []


def test_history_before_start_is_not_replayed() -> None:
    """订阅前已存在的告警不回放，只对订阅之后的新告警弹"""
    page = _FakePage()
    logs: ObservableList[LogEntryVM] = ObservableList([_log("ERROR", "旧错误")])
    from typing import Any, cast

    toaster = ErrorToaster(cast(Any, page), logs)
    toaster.start()
    # 锚点已设为历史末尾，旧错误不弹
    assert page.opened == []
    # 新错误才弹
    logs.append(_log("ERROR", "新错误"))
    assert len(page.opened) == 1
    assert "新错误" in _snackbar_text(page.opened[0])


def test_multiple_alerts_in_one_flush_merge_into_one() -> None:
    """一次 logs 更新内的多条告警合并为一个 SnackBar，显示累计条数"""
    page, logs, _ = _make()
    logs.extend([_log("WARNING", "甲"), _log("ERROR", "乙"), _log("WARNING", "丙")])
    assert len(page.opened) == 1
    text = _snackbar_text(page.opened[0])
    assert "丙" in text  # 最新一条
    assert "+2" in text  # 另有 2 条


def test_severe_uses_danger_color_warning_uses_warning_color() -> None:
    """含 ERROR/CRITICAL 用 danger 底色；纯 WARNING 用 warning 底色"""
    page, logs, _ = _make()
    logs.append(_log("WARNING"))
    assert page.opened[-1].bgcolor == PALETTE.warning
    logs.append(_log("ERROR"))
    assert page.opened[-1].bgcolor == PALETTE.danger


def test_stop_unsubscribes() -> None:
    """stop 后新告警不再弹"""
    page, logs, toaster = _make()
    toaster.stop()
    logs.append(_log("ERROR"))
    assert page.opened == []


def test_snackbar_is_non_blocking_floating() -> None:
    """SnackBar 为浮动行为且有时长（自动消失），保证不阻塞页面交互"""
    page, logs, _ = _make()
    logs.append(_log("ERROR"))
    snackbar = page.opened[0]
    assert snackbar.behavior == ft.SnackBarBehavior.FLOATING
    assert snackbar.duration and snackbar.duration > 0
