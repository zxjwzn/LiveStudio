"""在 qasync 事件循环上安全地跑后端协程

GUI 由按钮等同步槽触发后端异步操作。统一用 run_guarded 调度:它 ensure_future
协程并挂 done 回调,把未捕获异常交给可选的错误处理器(通常弹 InfoBar),
避免「Task exception was never retrieved」与异常静默丢失。
"""

import asyncio
from collections.abc import Awaitable, Callable

# 错误处理器:收到协程抛出的异常,自行决定如何呈现(如 InfoBar)。
ErrorHandler = Callable[[BaseException], None]


def run_guarded(
    coro: Awaitable[object],
    *,
    on_error: ErrorHandler | None = None,
) -> asyncio.Task[object]:
    """在当前事件循环调度协程,并对异常做统一兜底处理。

    返回 Task 便于调用方在需要时取消(如连接任务)。被取消不视为错误。
    """

    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda done: _report(done, on_error))
    return task


def _report(task: asyncio.Task[object], on_error: ErrorHandler | None) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    if on_error is not None:
        on_error(exc)
