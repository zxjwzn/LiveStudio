"""测试本机播放订阅方:源标识过滤、生命周期、格式转换、输出设备枚举"""

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
    """最小音频源:仅暴露 _publish_chunk,不接真实设备"""

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        self._clear_subscriptions()

    def emit(self, chunk: AudioChunk) -> None:
        self._publish_chunk(chunk)


class _FakeOutputStream:
    """sd.OutputStream 替身:记录构造参数,start/stop/close 不接真实设备"""

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
    """AudioChunk 必须带 source 标识(无默认),杜绝无源块"""

    with pytest.raises(TypeError):
        AudioChunk(  # type: ignore[call-arg]
            frames=1,
            samplerate=48000,
            channels=1,
            data=np.zeros(1, dtype=np.float32),
        )


def test_playback_config_defaults() -> None:
    """默认启用、仅放行 TTS(避免回放麦克风啸叫)"""

    config = PlaybackConfig()
    assert config.enabled is True
    assert config.sources == [AudioSourceKind.TTS]


def test_list_output_devices_filters_input_only(monkeypatch) -> None:
    """仅返回有输出声道的设备;纯输入设备(麦克风)被排除"""

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
    """int16 单声道 -> float32、复制到 2 声道、应用音量"""

    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=2, volume=0.5, output_device=0))
    sink._samplerate = 48000
    chunk = _chunk(16384, AudioSourceKind.TTS, channels=1, dtype=np.int16)
    pcm = sink._convert(chunk)

    assert pcm.dtype == np.float32
    assert pcm.size == 128 * 2  # 单声道复制到 2 声道
    expected = (16384 / 32768.0) * 0.5
    assert np.allclose(pcm.reshape(128, 2), expected)


def test_convert_downsamples() -> None:
    """块采样率高于输出采样率时下采样(48k -> 24k,帧数减半)"""

    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=1, output_device=0))
    sink._samplerate = 24000
    chunk = _chunk(0.0, AudioSourceKind.TTS, samplerate=48000, channels=1)
    pcm = sink._convert(chunk)
    assert pcm.size == 64  # 128 帧 @48k -> 64 帧 @24k


def test_convert_mono_to_stereo_mixdown() -> None:
    """多声道块混音到单声道(取均值)"""

    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(channels=1, output_device=0))
    sink._samplerate = 48000
    data = np.full((128, 2), 0.4, dtype=np.float32)
    chunk = AudioChunk(frames=128, samplerate=48000, channels=2, data=data, source=AudioSourceKind.TTS)
    pcm = sink._convert(chunk)
    assert pcm.size == 128
    assert np.allclose(pcm, 0.4)


async def test_sink_filters_by_source_kind(monkeypatch) -> None:
    """仅放行 sources 内的源:TTS 块开流并入缓冲,麦克风块被跳过"""

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

    source.emit(_chunk(0.5, AudioSourceKind.MICROPHONE))  # 被过滤
    source.emit(_chunk(0.5, AudioSourceKind.TTS))  # 放行
    await asyncio.sleep(0.1)  # 让 drain 处理(含 to_thread 开流)

    assert sink._stream is not None
    assert sink._buffer_frames > 0
    await sink.stop()
    assert not sink.is_started


async def test_sink_lifecycle_without_audio(monkeypatch) -> None:
    """无放行块时输出流懒开启(start/stop 生命周期正常,is_started 翻转)"""

    monkeypatch.setattr(playback_module.sd, "OutputStream", _FakeOutputStream)
    sink = AudioPlaybackSink(_DummySource(), PlaybackConfig(output_device=0))
    await sink.start()
    assert sink.is_started
    assert sink._stream is None  # 无音频,流未开
    await sink.stop()
    assert not sink.is_started
