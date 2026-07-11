"""字幕事件总线

镜像音频流(AudioStreamSource)的 pub/sub 模型:生产者(TTS 源)推送字幕事件,
消费者(网页 WS)订阅。发送频率由生产者控制,流只扇出(满则丢最旧,不调度)。
"""

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4


@dataclass(slots=True)
class SubtitleSegment:
    """一段字幕(词/字)及其在完整音频里的全局时间(秒)"""

    text: str
    start: float
    end: float


@dataclass(slots=True)
class SubtitleEvent:
    """字幕总线事件

    - ``begin``:一次发声开始;``text`` 全文
    - ``segments``:增量字幕段(仅新增段;start/end 为相对本句音频 0 点的全局秒)
    - ``finish``:发声结束(正常或被取消/被新发声取代)
    """

    kind: Literal["begin", "segments", "finish"]
    text: str | None = None
    segments: list[SubtitleSegment] | None = None


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

        self._publish(SubtitleEvent(kind="begin", text=text))

    def publish_segments(self, segments: list[SubtitleSegment]) -> None:
        """广播增量字幕段(仅新增段)"""

        if segments:
            self._publish(SubtitleEvent(kind="segments", segments=list(segments)))

    def finish(self) -> None:
        """发声结束:广播 finish"""

        self._publish(SubtitleEvent(kind="finish"))
