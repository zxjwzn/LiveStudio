"""在 qasync 事件循环上安全地跑后端协程

GUI 由按钮等同步槽触发后端异步操作。统一用 run_guarded 调度:它 ensure_future
协程并挂 done 回调,把未捕获异常交给可选的错误处理器(通常弹 InfoBar),
避免「Task exception was never retrieved」与异常静默丢失。
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from livestudio.utils.log import logger

# 错误处理器:收到协程抛出的异常,自行决定如何呈现(如 InfoBar)。
ErrorHandler = Callable[[BaseException], None]
# asyncio 事件循环异常处理器签名(供 set_exception_handler)。
ExceptionHandler = Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None]


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


def is_benign_proactor_connection_reset(context: dict[str, Any]) -> bool:
    """判断一个 asyncio 异常上下文是否为 Windows proactor 套接字拆除时的良性连接重置。

    CPython 3.12 的 ``_ProactorBasePipeTransport._call_connection_lost`` 在 connection_lost
    里直接 ``socket.shutdown(SHUT_RDWR)``;对端已 RST 时抛 ``ConnectionResetError``
    (WinError 10054)或 ``ConnectionAbortedError`` (10053),asyncio 把它当
    「Exception in callback ... _call_connection_lost」记 ERROR。连接本就要关,该报错
    源于平台层而非项目代码,GUI 停机强制收回 MCP 客户端长连等场景会刷屏--故判为良性。
    """

    exc = context.get("exception")
    if not isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
        return False
    return "_call_connection_lost" in str(context.get("message", ""))


def silence_proactor_connection_reset_on_close(loop: asyncio.AbstractEventLoop) -> None:
    """在 Windows 上屏蔽套接字拆除时的良性连接重置噪音(见 is_benign_proactor_connection_reset)。

    非 Windows 无 proactor、无此问题,空操作。其余异常照常走默认处理器。仅在 GUI 入口
    装一次,作用于整个 qasync 事件循环。
    """

    if os.name != "nt":
        return

    loop.set_exception_handler(proactor_reset_filter_handler(loop))


def proactor_reset_filter_handler(loop: asyncio.AbstractEventLoop) -> ExceptionHandler:
    """构造一个 asyncio 异常处理器:屏蔽良性连接重置,其余委托给 loop 默认处理器。"""

    default_handler = loop.default_exception_handler

    def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if is_benign_proactor_connection_reset(context):
            logger.debug("忽略 Windows proactor 套接字拆除时的良性连接重置: {}", context.get("exception"))
            return
        default_handler(context)

    return handler
