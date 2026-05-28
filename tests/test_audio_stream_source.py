"""AudioStreamSource 订阅与广播测试。

演示如何对一个抽象基类做最小子类化来测纯逻辑。
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from livestudio.services.audio_stream import AudioChunk, AudioStreamSource


class _DummySource(AudioStreamSource):
    """最小化实现：不接真实设备，只暴露 _publish_chunk 入口。"""

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        self.is_started = True

    async def stop(self) -> None:
        self.is_started = False
        self._clear_subscriptions()

    def emit(self, chunk: AudioChunk) -> None:
        self._publish_chunk(chunk)


def _make_chunk(value: float = 0.0) -> AudioChunk:
    samples = np.full((128, 1), value, dtype=np.float32)
    return AudioChunk(frames=128, samplerate=48000, channels=1, data=samples)


async def test_subscribe_receives_published_chunks() -> None:
    source = _DummySource()
    subscription = source.subscribe(queue_maxsize=4)

    chunk = _make_chunk(0.1)
    source.emit(chunk)

    received = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert received is chunk


async def test_unsubscribe_stops_delivery() -> None:
    source = _DummySource()
    subscription = source.subscribe(queue_maxsize=4)
    source.unsubscribe(subscription)

    source.emit(_make_chunk())

    assert subscription.queue.empty()


async def test_full_queue_drops_oldest_chunk() -> None:
    source = _DummySource()
    subscription = source.subscribe(queue_maxsize=2)

    first = _make_chunk(0.1)
    second = _make_chunk(0.2)
    third = _make_chunk(0.3)
    source.emit(first)
    source.emit(second)
    source.emit(third)

    # 队列容量 2，第一块应该被丢弃，留下 second/third
    delivered = [subscription.queue.get_nowait(), subscription.queue.get_nowait()]
    assert delivered == [second, third]
    assert subscription.queue.empty()


def test_subscribe_rejects_invalid_queue_size() -> None:
    source = _DummySource()
    with pytest.raises(ValueError):
        source.subscribe(queue_maxsize=0)
