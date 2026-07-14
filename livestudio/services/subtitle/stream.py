"""字幕事件总线

镜像音频流(AudioStreamSource)的 pub/sub 模型:生产者(TTS 源)推送字幕事件,
消费者(网页 WS)订阅。发送频率由生产者控制,流只扇出(满则丢最旧,不调度)。
"""

import asyncio
import contextlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from .models import SubtitleEvent, SubtitleEventKind, SubtitleSegment


@dataclass(frozen=True, slots=True)
class SubtitleSubscription:
    """字幕订阅句柄"""

    id: UUID
    queue: asyncio.Queue[SubtitleEvent]


class SubtitleStream:
    """字幕事件总线:生产者推送事件,消费者订阅(各持一个 asyncio.Queue,慢消费者丢最旧)。"""

    def __init__(self) -> None:
        self._subscriptions: dict[str, SubtitleSubscription] = {}

    def subscribe(self, *, queue_maxsize: int = 64) -> SubtitleSubscription:
        """订阅字幕事件"""

        if queue_maxsize < 1:
            raise ValueError("queue_maxsize 必须大于 0")
        subscription = SubtitleSubscription(
            id=uuid4(),
            queue=asyncio.Queue(maxsize=queue_maxsize),
        )
        self._subscriptions[str(subscription.id)] = subscription
        return subscription

    def unsubscribe(self, subscription: SubtitleSubscription) -> None:
        """取消订阅"""

        self._subscriptions.pop(str(subscription.id), None)

    def _clear_subscriptions(self) -> None:
        self._subscriptions.clear()

    def _publish(self, event: SubtitleEvent) -> None:
        """向全部订阅者扇出事件;慢订阅者丢最旧"""

        for subscription in tuple(self._subscriptions.values()):
            queue = subscription.queue
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    # --- 生产者 API(由 TTS 源调用)---

    def begin(self, text: str) -> None:
        """一次发声开始:广播 begin(全文)"""

        self._publish(SubtitleEvent(kind=SubtitleEventKind.BEGIN, text=text))

    def publish_segments(self, segments: list[SubtitleSegment]) -> None:
        """广播增量字幕段(仅新增段)"""

        if segments:
            self._publish(SubtitleEvent(kind=SubtitleEventKind.SEGMENTS, segments=list(segments)))

    def finish(self) -> None:
        """发声结束:广播 finish"""

        self._publish(SubtitleEvent(kind=SubtitleEventKind.FINISH))
