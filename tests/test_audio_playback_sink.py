"""测试音频播放订阅方:源标识过滤、生命周期、格式转换、输出设备枚举"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

import livestudio.services.audio_stream.playback as playback_module
from livestudio.services.audio_stream.base import AudioStreamSource
from livestudio.services.audio_stream.models import AudioChunk, AudioSourceKind
from livestudio.services.audio_stream.playback import (
    AudioPlaybackSink,
    OutputDeviceInfo,
    PlaybackConfig,
)


class _DummySource(AudioStreamSource):
    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        self._clear_subscriptions()

    def emit(self, chunk: AudioChunk) -> None:
        self._publish_chunk(chunk)


class _FakeOutputStream:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def _device_dict(
    name: str,
    *,
    outputs: int = 1,
    inputs: int = 0,
    samplerate: float = 48000.0,
) -> dict[str, Any]:
    return {
        "name": name,
        "max_input_channels": inputs,
        "max_output_channels": outputs,
        "default_samplerate": samplerate,
        "hostapi": 0,
    }


def _chunk(
    value: float,
    source: AudioSourceKind,
    *,
    samplerate: int = 48000,
    channels: int = 1,
    dtype: type = np.float32,
) -> AudioChunk:
    data = np.full((128, channels), value, dtype=dtype)
    return AudioChunk(
        frames=128,
        samplerate=samplerate,
        channels=channels,
        data=data,
        source=source,
    )


def test_audio_chunk_requires_source_kind() -> None:
    with pytest.raises(TypeError):
        AudioChunk(  # type: ignore[call-arg]
            frames=1,
            samplerate=48000,
            channels=1,
            data=np.zeros(1, dtype=np.float32),
        )


def test_playback_config_defaults() -> None:
    config = PlaybackConfig()
    assert config.enabled is True
    assert config.sources == [AudioSourceKind.TTS]


def test_list_output_devices_filters_input_only(monkeypatch) -> None:
    monkeypatch.setattr(
        playback_module.sd,
        "query_devices",
        lambda: [
            _device_dict("扬声器", outputs=2, inputs=0),
            _device_dict("麦克风", outputs=0, inputs=2),
            _device_dict("虚拟声卡", outputs=2, inputs=2),
        ],
    )
    devices = AudioPlaybackSink.list_output_devices()
    assert [d.name for d in devices] == ["扬声器", "虚拟声卡"]
    assert all(d.max_output_channels > 0 for d in devices)
    assert isinstance(devices[0], OutputDeviceInfo)


def test_convert_int16_to_float32_stereo_volume() -> None:
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=2, volume=0.5, output_device=0))
    sink._samplerate = 48000
    chunk = _chunk(16384, AudioSourceKind.TTS, channels=1, dtype=np.int16)
    pcm = sink._convert(chunk)

    assert pcm.dtype == np.float32
    assert pcm.size == 128 * 2
    expected = (16384 / 32768.0) * 0.5
    assert np.allclose(pcm.reshape(128, 2), expected)


def test_convert_downsamples() -> None:
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=1, output_device=0))
    sink._samplerate = 24000
    chunk = _chunk(0.0, AudioSourceKind.TTS, samplerate=48000, channels=1)
    pcm = sink._convert(chunk)
    assert pcm.size == 64


def test_convert_mono_to_stereo_mixdown() -> None:
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=1, output_device=0))
    sink._samplerate = 48000
    data = np.full((128, 2), 0.4, dtype=np.float32)
    chunk = AudioChunk(frames=128, samplerate=48000, channels=2, data=data, source=AudioSourceKind.TTS)
    pcm = sink._convert(chunk)
    assert pcm.size == 128
    assert np.allclose(pcm, 0.4)


async def test_sink_filters_by_source_kind(monkeypatch) -> None:
    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        playback_module.sd,
        "query_devices",
        lambda *args: _device_dict("out") if args else [_device_dict("out")],
    )

    source = _DummySource()
    config = PlaybackConfig(sources=[AudioSourceKind.TTS], output_device=0)
    sink = AudioPlaybackSink(source, config)
    await sink.start()

    source.emit(_chunk(0.5, AudioSourceKind.MICROPHONE))
    source.emit(_chunk(0.5, AudioSourceKind.TTS))
    await asyncio.sleep(0.1)

    assert sink._stream is not None
    assert sink._buffer_frames > 0
    await sink.stop()
    assert not sink.is_started


async def test_sink_lifecycle_without_audio(monkeypatch) -> None:
    """无 prepare、无放行块时输出流懒开启(流未开)"""

    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(output_device=0))
    await sink.start()
    assert sink.is_started
    assert sink._stream is None
    await sink.stop()
    assert not sink.is_started


async def test_prepare_opens_stream_without_cushion(monkeypatch) -> None:
    """prepare 打开输出流且不预填静音垫(唇音同源时钟)"""

    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        playback_module.sd,
        "query_devices",
        lambda *args: _device_dict("out") if args else [_device_dict("out")],
    )
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(sources=[AudioSourceKind.TTS], output_device=0))
    await sink.start()
    assert sink._stream is None
    await sink.prepare()
    assert sink._stream is not None
    assert sink._buffer_frames == 0  # 无静音垫
    await sink.stop()


async def test_flush_clears_buffer_and_subscription_queue(monkeypatch) -> None:
    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        playback_module.sd,
        "query_devices",
        lambda *args: _device_dict("out") if args else [_device_dict("out")],
    )

    source = _DummySource()
    sink = AudioPlaybackSink(source, PlaybackConfig(sources=[AudioSourceKind.TTS], output_device=0))
    await sink.start()
    await sink.prepare()
    source.emit(_chunk(0.5, AudioSourceKind.TTS))
    await asyncio.sleep(0.1)
    assert sink._buffer_frames > 0

    assert sink._subscription is not None
    sink._subscription.queue.put_nowait(_chunk(0.9, AudioSourceKind.TTS))
    assert not sink._subscription.queue.empty()

    sink.flush()
    assert sink._buffer_frames == 0
    assert sink._remainder is None
    assert sink._subscription.queue.empty()
    await sink.stop()

async def test_prepare_first_audio_prefills_jitter(monkeypatch) -> None:
    """首批真实音频前预填 jitter 静音,缓冲非空但远小于旧 100ms 垫"""

    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        playback_module.sd,
        "query_devices",
        lambda *args: _device_dict("out", samplerate=48000.0) if args else [_device_dict("out")],
    )
    source = _DummySource()
    sink = AudioPlaybackSink(
        source,
        PlaybackConfig(sources=[AudioSourceKind.TTS], output_device=0, samplerate=48000),
    )
    await sink.start()
    await sink.prepare()
    assert sink._buffer_frames == 0
    source.emit(_chunk(0.5, AudioSourceKind.TTS, samplerate=48000))
    await asyncio.sleep(0.05)
    # jitter(~800@48k) + 真实块(可能重采样后仍 >0)
    assert sink._buffer_frames > 0
    # 不应再有 0.1s=4800 级静音垫
    assert sink._buffer_frames < int(48000 * 0.08)
    await sink.stop()


def test_apply_fade_in_ramps_from_zero() -> None:
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=1, output_device=0))
    sink._channels = 1
    sink._fade_in_remaining = 4
    pcm = np.ones(8, dtype=np.float32)
    out = sink._apply_fade_in(pcm)
    assert out[0] == 0.0
    assert out[3] == pytest.approx(1.0)
    assert np.allclose(out[4:], 1.0)
    assert sink._fade_in_remaining == 0

