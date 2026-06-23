"""日志控制器：把 loguru 输出桥接到 AppState.logs。

loguru sink 可能在任意线程触发（enqueue=True 时在专用线程），因此 sink 只往
线程安全的 deque 追加，由事件循环内的 drain 任务批量（默认 100ms）刷入状态，
既保证线程安全，又避免高频日志逐条刷 UI。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from typing import TYPE_CHECKING

from livestudio.utils.log import logger

if TYPE_CHECKING:
    # loguru.Message 是运行时内部 str 子类，仅类型存根导出；__future__ annotations
    # 让注解不在运行时求值，故用 TYPE_CHECKING 守卫导入，运行时零开销。
    from loguru import Message

from ..core.app_state import AppState
from ..core.theme import level_color
from ..core.view_models import LogEntryVM

# 日志环形缓冲上限与批量刷新间隔
_LOG_CAP = 2000
_FLUSH_SECONDS = 0.1


class LogController:
    """注册 loguru sink，缓冲并批量刷入 state.logs。"""

    def __init__(self, state: AppState) -> None:
        self.state = state
        self._buffer: deque[LogEntryVM] = deque(maxlen=_LOG_CAP)
        self._sink_id: int | None = None
        self._drain_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """注册 sink 并启动 drain 任务。"""

        if self._sink_id is None:
            self._sink_id = logger.add(
                self._sink,
                level="DEBUG",
                enqueue=True,
                backtrace=False,
                diagnose=False,
            )
        if self._drain_task is None:
            self._drain_task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        """移除 sink 并停止 drain 任务。"""

        task = self._drain_task
        self._drain_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._sink_id is not None:
            with contextlib.suppress(Exception):
                logger.remove(self._sink_id)
            self._sink_id = None
        # 显式收尾刷新：任务在首次执行前被取消时，CancelledError 会在 try 之前
        # 抛出，drain_loop 内的兜底 flush 不会执行，这里确保缓冲不丢。
        self._flush()

    def _sink(self, message: Message) -> None:
        """loguru sink：在任意线程被调用，仅做无锁追加。"""

        # loguru.Message 是 str 子类，.record 恒存在，直接取无需 getattr 兜底
        record = message.record
        level_name = record["level"].name
        entry = LogEntryVM(
            ts=record["time"].strftime("%H:%M:%S.%f")[:-3],
            level=level_name,
            message=record["message"],
            color=level_color(level_name),
        )
        self._buffer.append(entry)

    async def _drain_loop(self) -> None:
        """周期性把缓冲批量刷入状态（在事件循环线程内执行）。"""

        try:
            while True:
                await asyncio.sleep(_FLUSH_SECONDS)
                self._flush()
        except asyncio.CancelledError:
            self._flush()
            raise

    def _flush(self) -> None:
        """把当前缓冲的全部日志合并写入 state.logs。"""

        if not self._buffer:
            return
        pending = []
        while self._buffer:
            pending.append(self._buffer.popleft())
        self.state.logs.extend(pending, cap=_LOG_CAP)
