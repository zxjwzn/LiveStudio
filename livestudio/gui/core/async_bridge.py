"""跨线程 → Flet 事件循环 marshaling

音频回调、loguru sink、平台后台 task 可能不在 Flet 的事件循环线程。
所有写 AppState 的操作统一经 AsyncBridge.post() 调度回事件循环线程，
保证 Observable 通知与 page.update() 在 UI 线程串行执行。
"""

from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft


class AsyncBridge:
    """把任意线程的调用安全 marshal 到 Flet 事件循环。"""

    def __init__(self, page: ft.Page, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self.page = page
        self._loop = loop or asyncio.get_event_loop()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """显式绑定事件循环（在 async 入口内拿到 running loop 时调用）。"""

        self._loop = loop

    def post(self, fn: Callable[[], None]) -> None:
        """从任意线程安全调度 fn 到 Flet 事件循环。"""

        self._loop.call_soon_threadsafe(fn)

    def post_update(self, *controls: ft.Control) -> None:
        """调度一次 page.update()（可指定局部控件）。"""

        self.post(lambda: self.page.update(*controls))
