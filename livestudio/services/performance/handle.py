"""表演动作生命周期句柄

调度器只 await 公共契约,不向能力层注入回调。
能力(TTS / 表情等)返回结构兼容本协议的会话对象即可。
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class ActionHandle(Protocol):
    """一次异步表演动作的生命周期。

    - ``wait_started``: 真实开始(如首帧上总线、表情生效)
    - ``wait_ended``: 表演语义结束(呈现结束 / hold 退出);收尾可在后台继续
    - ``cancel``: 协作取消(幂等);应尽快使 wait_* 解除阻塞
    """

    @property
    def started(self) -> bool:
        """是否已进入 started。"""
        ...

    @property
    def ended(self) -> bool:
        """是否已结束。"""
        ...

    async def wait_started(self) -> None:
        """等到 started(已 started 则立即返回)。"""
        ...

    async def wait_ended(self) -> None:
        """等到 ended(已 ended 则立即返回)。"""
        ...

    async def cancel(self) -> None:
        """取消本动作(幂等)。"""
        ...


class EventActionHandle:
    """基于 asyncio.Event 的通用 Handle 实现(测试桩 / 瞬时动作可复用)。"""

    def __init__(self) -> None:
        self._started = asyncio.Event()
        self._ended = asyncio.Event()

    @property
    def started(self) -> bool:
        return self._started.is_set()

    @property
    def ended(self) -> bool:
        return self._ended.is_set()

    def mark_started(self) -> None:
        self._started.set()

    def mark_ended(self) -> None:
        """结束;若尚未 start 则一并 start,避免 wait_started 永久挂起。"""

        self._started.set()
        self._ended.set()

    async def wait_started(self) -> None:
        await self._started.wait()

    async def wait_ended(self) -> None:
        await self._ended.wait()

    async def cancel(self) -> None:
        self.mark_ended()
