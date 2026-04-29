"""通用音频流抽象接口。"""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from uuid import uuid4

from .models import AudioChunk, AudioChunkSubscription


class AudioStreamSource(ABC):
    """统一音频流来源抽象。"""

    def __init__(self):
        self.is_started = False
        self._subscriptions: dict[str, AudioChunkSubscription] = {}

    @abstractmethod
    async def initialize(self) -> None:
        """初始化音频源。"""

    @abstractmethod
    async def start(self) -> None:
        """启动音频源。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止音频源。"""

    async def restart(self) -> None:
        """重启音频源。"""

        await self.stop()
        await self.initialize()
        await self.start()

    def subscribe(self, *, queue_maxsize: int = 32) -> AudioChunkSubscription:
        """订阅当前音频源发布的音频块。"""

        if queue_maxsize < 1:
            raise ValueError("queue_maxsize 必须大于 0")
        subscription = AudioChunkSubscription(
            id=uuid4(),
            queue=asyncio.Queue(maxsize=queue_maxsize),
        )
        self._subscriptions[str(subscription.id)] = subscription
        return subscription

    def unsubscribe(self, subscription: AudioChunkSubscription) -> None:
        """取消音频块订阅。"""

        self._subscriptions.pop(str(subscription.id), None)

    def _clear_subscriptions(self) -> None:
        """清空全部音频块订阅。"""

        self._subscriptions.clear()

    def _publish_chunk(self, chunk: AudioChunk) -> None:
        """向全部订阅者广播音频块；慢订阅者会丢弃最旧音频块。"""

        for subscription in tuple(self._subscriptions.values()):
            queue = subscription.queue
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(chunk)
