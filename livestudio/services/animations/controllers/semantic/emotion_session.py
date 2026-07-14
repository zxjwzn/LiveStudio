"""表情 oneshot 会话:领域生命周期,供调度器 await。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .expression import ExpressionController


class EmotionSession:
    """一次 play_emotion 的表演生命周期。

    - started: 表情已应用(native 下发后)
    - ended: hold 退出、开始回中性(恢复可在后台继续)
    """

    def __init__(self, controller: ExpressionController) -> None:
        self._controller = controller
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

    def mark_ended(self, *, force: bool = False) -> None:
        if force:
            self._started.set()
            self._ended.set()
            return
        if not self._started.is_set():
            return
        self._ended.set()

    async def wait_started(self) -> None:
        await self._started.wait()

    async def wait_ended(self) -> None:
        await self._ended.wait()

    async def cancel(self) -> None:
        """协作结束 hold(幂等);ended 由控制器在 hold 退出后 mark。"""

        if self._ended.is_set():
            return
        if self._controller.current_session is self:
            await self._controller.release_hold()
