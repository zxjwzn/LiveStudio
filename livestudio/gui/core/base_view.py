"""视图基类：统一管理 Observable 订阅的生命周期。

约定：
- 子类实现 ``build_content()`` 返回静态结构（在 ``__init__`` 阶段调用）。
  注意不要用 ``build``：那是 flet ``Control`` 的保留方法（返回 None），
  覆盖它会造成签名不兼容。
- 子类实现 ``bind()`` 建立订阅，统一用 ``self.watch(...)`` 登记。
- 订阅在 ``did_mount`` 建立（此时 ``self.page`` 已就绪），在
  ``will_unmount`` 自动全部退订，避免视图被缓存复用时泄漏。
"""

from __future__ import annotations

from typing import Awaitable, Callable

import flet as ft

from .observable import Observable
from .view_context import ViewContext


class BaseView(ft.Container):
    """所有页面视图的基类。"""

    def __init__(self, ctx: ViewContext) -> None:
        super().__init__(expand=True)
        self.ctx = ctx
        self.state = ctx.state
        self._unsubs: list[Callable[[], None]] = []
        self.content = self.build_content()

    # —— 子类实现 ——
    def build_content(self) -> ft.Control:
        """构建并返回视图静态结构。"""

        raise NotImplementedError

    def bind(self) -> None:
        """建立 Observable 订阅；默认无订阅。"""

    # —— 订阅工具 ——
    def watch(self, observable: Observable, handler: Callable, *, immediate: bool = True) -> None:
        """订阅 ``observable`` 并登记退订句柄，由 ``will_unmount`` 统一释放。"""

        self._unsubs.append(observable.subscribe(handler, immediate=immediate))

    def safe_update(self) -> None:
        """仅在已挂载时刷新，避免未挂载控件 update 报错。"""

        if self.page is not None:
            self.update()

    def run_intent(self, coro_factory: Callable[[], Awaitable[object]]) -> None:
        """在事件循环内调度一个异步意图（供 Flet 同步事件处理器转发到 bridge）。

        coro_factory 是无参可调用，返回协程；仅在已挂载（self.page 可用）时调度。
        page.run_task 断言传入的是协程函数（asyncio.iscoroutinefunction），普通
        lambda 不满足，故用 async 包装器把 coro_factory 适配为协程函数。
        """

        if self.page is None:
            return

        async def _runner() -> None:
            await coro_factory()

        self.page.run_task(_runner)

    # —— Flet 生命周期钩子 ——
    def did_mount(self) -> None:
        self.bind()

    def will_unmount(self) -> None:
        for unsubscribe in self._unsubs:
            unsubscribe()
        self._unsubs.clear()
