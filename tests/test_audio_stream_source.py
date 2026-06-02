"""AudioStreamSource 订阅与广播测试。

演示如何对一个抽象基类做最小子类化来测纯逻辑。
"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from livestudio.services.audio_stream import (
    AudioChunk,
    AudioSourceKind,
    AudioStreamConfigFile,
    AudioStreamRouter,
    AudioStreamSource,
)
from livestudio.services.audio_stream.sources.microphone import (
    microphone as microphone_module,
)
from livestudio.services.audio_stream.sources.microphone.config import (
    MicrophoneAudioStreamConfig,
)
from livestudio.services.audio_stream.sources.microphone.microphone import (
    MicrophoneAudioStreamSource,
)
from livestudio.services.audio_stream.sources.microphone.models import InputDeviceInfo


class _DummySource(AudioStreamSource):
    """最小化实现：不接真实设备，只暴露 _publish_chunk 入口。"""

    def __init__(self, *, fail_start: bool = False) -> None:
        super().__init__()
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("source start failed")
        self.is_started = True

    async def stop(self) -> None:
        self.stop_calls += 1
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


async def test_router_switch_source_rolls_back_when_new_source_fails() -> None:
    router = AudioStreamRouter()
    router.config_manager = type(
        "_ConfigManager",
        (),
        {
            "config": AudioStreamConfigFile(),
            "save_calls": 0,
            "save": lambda self: _save_config(self),
        },
    )()
    microphone = _DummySource()
    tts = _DummySource(fail_start=True)
    router._microphone_source = microphone
    router._tts_source = tts
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)
    router._initialized = True
    router.is_started = True
    await microphone.start()
    router._forward_task = asyncio.create_task(router._forward_chunks())

    with pytest.raises(RuntimeError, match="source start failed"):
        await router.switch_source(AudioSourceKind.TTS)

    assert router.active_source_kind is AudioSourceKind.MICROPHONE
    assert router.config.source is AudioSourceKind.MICROPHONE
    assert microphone.is_started
    assert not tts.is_started
    assert router._source_subscription is not None
    assert router._forward_task is not None
    await router.stop()


async def test_microphone_start_closes_stream_when_start_fails(monkeypatch) -> None:
    stream = _FakeInputStream(fail_start=True)
    monkeypatch.setattr(microphone_module.sd, "InputStream", lambda **_: stream)
    source = MicrophoneAudioStreamSource(MicrophoneAudioStreamConfig())
    source._loop = asyncio.get_running_loop()
    source._device_info = InputDeviceInfo(
        index=1,
        name="mic",
        max_input_channels=1,
        default_samplerate=48000.0,
        hostapi=0,
    )

    with pytest.raises(RuntimeError, match="stream start failed"):
        await source.start()

    assert stream.closed
    assert source._stream is None
    assert not source.is_started


async def test_microphone_stop_clears_state_when_stream_stop_fails() -> None:
    source = MicrophoneAudioStreamSource(MicrophoneAudioStreamConfig())
    source._loop = asyncio.get_running_loop()
    source._device_info = InputDeviceInfo(
        index=1,
        name="mic",
        max_input_channels=1,
        default_samplerate=48000.0,
        hostapi=0,
    )
    source._stream = _FakeInputStream(fail_stop=True)
    source.is_started = True
    subscription = source.subscribe(queue_maxsize=4)

    with pytest.raises(RuntimeError, match="stream stop failed"):
        await source.stop()

    assert source._stream is None
    assert source._loop is None
    assert source._device_info is None
    assert not source.is_started
    assert str(subscription.id) not in source._subscriptions


async def _save_config(config_manager: Any) -> None:
    config_manager.save_calls += 1


class _FakeInputStream:
    def __init__(self, *, fail_start: bool = False, fail_stop: bool = False) -> None:
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.started = False
        self.closed = False

    def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("stream start failed")
        self.started = True

    def stop(self) -> None:
        if self.fail_stop:
            raise RuntimeError("stream stop failed")
        self.started = False

    def close(self) -> None:
        self.closed = True
