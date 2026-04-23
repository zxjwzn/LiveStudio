"""用于 VTube Studio 事件的基于队列的监听器基础组件。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .models import VTSEventEnvelope

EventQueueHandler = Callable[[VTSEventEnvelope], Awaitable[None] | None]


class VTSEventListener:
    """基于队列的事件监听器。"""

    def __init__(self, event_name: str, queue_size: int) -> None:
        self.event_name = event_name
        self.handler: EventQueueHandler | None = None
        self._queue: asyncio.Queue[VTSEventEnvelope] = asyncio.Queue(maxsize=queue_size)

    async def push(self, event: VTSEventEnvelope) -> None:
        """推送事件到监听队列。"""

        if self._queue.full():
            _ = self._queue.get_nowait()
            self._queue.task_done()
        await self._queue.put(event)

    async def next_event(self, timeout: float | None = None) -> VTSEventEnvelope:
        """等待下一条事件。"""

        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    def empty(self) -> bool:
        """当前队列是否为空。"""

        return self._queue.empty()
