"""通用音频流抽象接口"""

import asyncio
import contextlib
from abc import ABC
from uuid import uuid4

from livestudio.services.lifecycle import AsyncServiceLifecycleMixin

from .models import AudioChunk, AudioChunkSubscription


class AudioStreamSource(AsyncServiceLifecycleMixin, ABC):
    """统一音频流来源抽象。

    生命周期统一走 ``AsyncServiceLifecycleMixin`` 的 start/restart/stop
    三件套：子类只实现 ``_do_start`` / ``_do_stop``（按需重写
    ``_do_restart``）副作用，幂等守卫、标志维护与失败回滚由 Mixin 统一处理。
    其中 ``stop`` 是唯一真正释放资源的终止入口（会清空订阅）。
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, AudioChunkSubscription] = {}

    def subscribe(self, *, queue_maxsize: int = 32) -> AudioChunkSubscription:
        """订阅当前音频源发布的音频块"""

        if queue_maxsize < 1:
            raise ValueError("queue_maxsize 必须大于 0")
        subscription = AudioChunkSubscription(
            id=uuid4(),
            queue=asyncio.Queue(maxsize=queue_maxsize),
        )
        self._subscriptions[str(subscription.id)] = subscription
        return subscription

    def unsubscribe(self, subscription: AudioChunkSubscription) -> None:
        """取消音频块订阅"""

        self._subscriptions.pop(str(subscription.id), None)

    def _clear_subscriptions(self) -> None:
        """清空全部音频块订阅"""

        self._subscriptions.clear()

    def _publish_chunk(self, chunk: AudioChunk) -> None:
        """向全部订阅者广播音频块；慢订阅者会丢弃最旧音频块"""

        for subscription in tuple(self._subscriptions.values()):
            queue = subscription.queue
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(chunk)
