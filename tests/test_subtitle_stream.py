"""测试字幕事件总线(镜像音频流 pub/sub)"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio

import pytest

from livestudio.services.subtitle import (
    SubtitleSegment,
    SubtitleStream,
)


async def test_subtitle_stream_subscribe_receives_events() -> None:
    """订阅者收到 begin/segments/finish,内容正确"""

    stream = SubtitleStream()
    sub = stream.subscribe(queue_maxsize=8)
    stream.begin("hello")
    stream.publish_segments([SubtitleSegment(text="he", start=0.0, end=0.3)])
    stream.finish()

    events = []
    while not sub.queue.empty():
        events.append(sub.queue.get_nowait())

    assert [e.kind for e in events] == ["begin", "segments", "finish"]
    assert events[0].text == "hello"
    assert events[1].segments[0].text == "he"
    assert events[1].segments[0].start == 0.0


async def test_subtitle_stream_unsubscribe_stops_delivery() -> None:
    """退订后不再收到事件"""

    stream = SubtitleStream()
    sub = stream.subscribe(queue_maxsize=8)
    stream.unsubscribe(sub)
    stream.begin("x")

    assert sub.queue.empty()


def test_subtitle_stream_full_queue_drops_oldest() -> None:
    """满队丢最旧(同音频流)"""

    stream = SubtitleStream()
    sub = stream.subscribe(queue_maxsize=2)
    stream.begin("a")
    stream.begin("b")
    stream.begin("c")  # 队列容量 2,"a" 被丢

    delivered = [sub.queue.get_nowait(), sub.queue.get_nowait()]
    assert [e.text for e in delivered] == ["b", "c"]
    assert sub.queue.empty()


def test_subtitle_stream_publish_empty_segments_is_noop() -> None:
    """空段列表不发布"""

    stream = SubtitleStream()
    sub = stream.subscribe(queue_maxsize=8)
    stream.publish_segments([])

    assert sub.queue.empty()


def test_subtitle_stream_subscribe_rejects_invalid_queue_size() -> None:
    """queue_maxsize 必须 > 0"""

    stream = SubtitleStream()
    with pytest.raises(ValueError):
        stream.subscribe(queue_maxsize=0)


async def test_subtitle_stream_no_subscriber_publish_is_noop() -> None:
    """无订阅者时发布不报错(空操作)"""

    stream = SubtitleStream()
    stream.begin("x")  # 无订阅者
    stream.publish_segments([SubtitleSegment(text="x", start=0.0, end=0.1)])
    stream.finish()

    # 订阅后只收新事件
    sub = stream.subscribe(queue_maxsize=8)
    await asyncio.sleep(0)
    assert sub.queue.empty()
