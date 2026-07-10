"""测试 AudioStreamSource 的订阅和广播

演示如何对一个抽象基类做最小子类化来测纯逻辑
"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

import numpy as np
import pytest

from livestudio.config import ConfigManager
from livestudio.services.audio_stream import (
    AudioChunk,
    AudioSourceKind,
    AudioStreamRouter,
    AudioStreamRouterConfig,
    AudioStreamSource,
)
from livestudio.services.audio_stream.playback import PlaybackConfig
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
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.services.audio_stream.sources.tts.tts import TTSAudioStreamSource


class _DummySource(AudioStreamSource):
    """最小化实现：不接真实设备，只暴露 _publish_chunk 入口。

    走 Mixin 模板方法（_do_start/_do_stop/_do_restart），忠实复刻真实音频源的
    生命周期语义：stop 清空订阅（真正退出），restart 软重启但保留订阅
    （路由器对本源的转发订阅得以存活）。
    """

    def __init__(self, *, fail_start: bool = False) -> None:
        super().__init__()
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0

    async def _do_start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("source start failed")

    async def _do_stop(self) -> None:
        self.stop_calls += 1
        self._clear_subscriptions()

    async def _do_restart(self) -> None:
        # 软重启：回收并重建运行态，但**不**清空订阅
        self.stop_calls += 1
        self.start_calls += 1

    def emit(self, chunk: AudioChunk) -> None:
        self._publish_chunk(chunk)


def _make_chunk(value: float = 0.0) -> AudioChunk:
    samples = np.full((128, 1), value, dtype=np.float32)
    return AudioChunk(
        frames=128,
        samplerate=48000,
        channels=1,
        data=samples,
        source=AudioSourceKind.MICROPHONE,
    )


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


async def test_source_restart_preserves_subscriptions_but_stop_clears_them() -> None:
    """源软重启保留自身订阅；stop 才真正清空——这是路由器转发订阅得以存活的根基。

    路由器对源持有一个转发订阅（_source_subscription）。换设备走 source.restart()
    时，该订阅必须存活，否则重启后路由器收不到音频块。stop 是唯一真正退出，会清空。
    """
    source = _DummySource()
    subscription = source.subscribe(queue_maxsize=4)
    await source.start()
    assert str(subscription.id) in source._subscriptions

    # 软重启：订阅原样保留，且重启后仍能收到音频块
    await source.restart()
    assert source.is_started
    assert str(subscription.id) in source._subscriptions
    chunk = _make_chunk(0.5)
    source.emit(chunk)
    received = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert received is chunk

    # stop 是真正退出：清空订阅、复位标志
    await source.stop()
    assert not source.is_started
    assert str(subscription.id) not in source._subscriptions


async def test_tts_audio_source_start_stop_lifecycle() -> None:
    source = TTSAudioStreamSource(TTSAudioStreamConfig())

    await source.start()
    assert source.is_started

    await source.stop()
    assert not source.is_started


async def test_tts_idle_emits_silence_chunks() -> None:
    """TTS 源启动后、未发声时持续发布响度 0 的静音块(source=TTS)"""

    source = TTSAudioStreamSource(TTSAudioStreamConfig())
    subscription = source.subscribe(queue_maxsize=8)
    await source.start()

    chunk = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert chunk.source is AudioSourceKind.TTS
    assert float(np.max(np.abs(chunk.data))) == 0.0  # 静音

    await source.stop()
    assert not source.is_started


async def test_tts_speak_emits_non_silence() -> None:
    """speak 发声期间发布非静音块(正弦音)"""

    source = TTSAudioStreamSource(TTSAudioStreamConfig())
    subscription = source.subscribe(queue_maxsize=64)
    await source.start()
    await asyncio.sleep(0.03)  # 让初始静音块入队
    while not subscription.queue.empty():
        subscription.queue.get_nowait()

    source.speak("hi", duration=0.3, frequency=440.0)
    await asyncio.sleep(0.1)  # 让发声产出若干块
    await source.stop()  # 停掉发声与空闲循环,停止生产

    chunks: list[AudioChunk] = []
    while not subscription.queue.empty():
        chunks.append(subscription.queue.get_nowait())
    assert chunks, "发声期间应收到音频块"
    assert any(float(np.max(np.abs(c.data))) > 0.0 for c in chunks), "应含非静音(正弦音)块"


async def test_router_switch_source_rolls_back_when_new_source_fails() -> None:
    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    microphone = _DummySource()
    tts = _DummySource(fail_start=True)
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = cast(Any, tts)
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)
    router._mark_started()
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


async def test_router_forwards_active_source_chunks_to_subscribers() -> None:
    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    microphone = _DummySource()
    tts = _DummySource()
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = cast(Any, tts)
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)

    subscriber = router.subscribe(queue_maxsize=4)
    await router.start()
    chunk = _make_chunk(0.4)
    microphone.emit(chunk)

    received = await asyncio.wait_for(subscriber.queue.get(), timeout=0.5)

    assert received is chunk
    await router.stop()


async def test_restart_active_source_keeps_downstream_subscribers() -> None:
    """软重启活动源后，路由器对外的下游订阅仍存活并继续收到音频块。

    回归：用 stop+start 重启整个路由器会 _clear_subscriptions 清掉下游订阅
    （如 MouthSync），导致换设备后无音频。restart 是软重启，只委托活动源自身
    软重启（保留其订阅），路由器对外的下游订阅必须原样保留。
    """
    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    microphone = _DummySource()
    tts = _DummySource()
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = cast(Any, tts)
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)

    # 模拟一个下游订阅者（如 MouthSyncController 在 app 启动时订阅一次）
    downstream = router.subscribe(queue_maxsize=4)
    await router.start()

    # 就地软重启活动源（换设备等配置生效）
    await router.restart()

    # 源被停了又起（物理流重建）
    assert microphone.stop_calls >= 1
    assert microphone.start_calls >= 2

    # 关键：下游订阅没被清掉，重启后仍能收到音频块
    chunk = _make_chunk(0.7)
    microphone.emit(chunk)
    received = await asyncio.wait_for(downstream.queue.get(), timeout=0.5)
    assert received is chunk

    await router.stop()


async def test_reload_source_preserves_downstream_subscriptions() -> None:
    """reload_source 重建活动源实例但不清空对外下游订阅(MouthSyncController 等)。

    回归:save_microphone_config/save_tts_config 原走 stop+start,会 _clear_subscriptions
    清掉下游订阅,导致保存后唇形同步收不到音频块。reload_source 只重建内部源、保留下游。
    """

    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    router.config.playback.enabled = False  # 关本机播放,避免测试开真实输出流
    microphone = _DummySource()
    tts = _DummySource()
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = cast(Any, tts)
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.TTS
    router._source_subscription = tts.subscribe(queue_maxsize=4)

    downstream = router.subscribe(queue_maxsize=4)  # 模拟 MouthSyncController 的订阅
    await router.start()

    # 重建活动 TTS 源(内部用真实 TTSAudioStreamSource 替换 _DummySource 并重启转发)
    await router.reload_source(AudioSourceKind.TTS)

    # 关键:对外下游订阅未被清空,reload 后仍能收到新 TTS 源的静音块
    received = await asyncio.wait_for(downstream.queue.get(), timeout=1.0)
    assert received.source is AudioSourceKind.TTS

    await router.stop()


def _device(index: int, name: str) -> InputDeviceInfo:
    return InputDeviceInfo(
        index=index,
        name=name,
        max_input_channels=1,
        default_samplerate=48000.0,
        hostapi=0,
    )


async def test_microphone_start_falls_back_to_default_device(monkeypatch) -> None:
    """配置设备打不开时回退默认设备：成功出声，但不得回写 config（回归）。

    设备被占用/拔出会让 sd.InputStream 打开失败（PaErrorCode -9996），此时应回退到
    系统默认输入设备重试，而非让整条管线崩溃。回退仅改运行态 _device_info，
    config 代表用户意图（这里留空=自动），不被某次回退结果覆盖。
    """
    configured = _device(1, "坏设备")
    default = _device(9, "默认设备")

    def _input_stream(*, device: int, **_: object) -> _FakeInputStream:
        # 配置设备(1)打开失败，默认设备(9)成功
        return _FakeInputStream(fail_start=device == 1)

    monkeypatch.setattr(microphone_module.sd, "InputStream", _input_stream)

    source = MicrophoneAudioStreamSource(MicrophoneAudioStreamConfig())

    async def _list() -> list[InputDeviceInfo]:
        return [configured, default]

    async def _resolve_input() -> InputDeviceInfo:
        return configured  # 解析得到配置设备(1)，随后 _open_stream 打不开触发回退

    async def _resolve_default(_devices: object) -> InputDeviceInfo:
        return default

    monkeypatch.setattr(source, "list_input_devices", _list)
    monkeypatch.setattr(source, "_resolve_input_device", _resolve_input)
    monkeypatch.setattr(source, "_resolve_default_device", _resolve_default)

    await source.start()

    assert source.is_started
    assert source._device_info is default
    # 回退只改运行态，config 保持用户原意（留空），不被回退设备覆盖
    assert source.config.device_name is None
    assert source.config.device_index is None
    await source.stop()


async def test_microphone_start_raises_when_no_fallback_available(monkeypatch) -> None:
    """配置设备与默认设备都打不开时抛错并清理干净（无可回退设备）。"""
    only = _device(1, "唯一设备")
    stream = _FakeInputStream(fail_start=True)
    monkeypatch.setattr(microphone_module.sd, "InputStream", lambda **_: stream)

    source = MicrophoneAudioStreamSource(MicrophoneAudioStreamConfig())

    async def _list() -> list[InputDeviceInfo]:
        return [only]

    async def _resolve_input() -> InputDeviceInfo:
        return only

    async def _resolve_default(_devices: object) -> InputDeviceInfo:
        return only  # 默认设备就是配置设备本身 → 无可回退

    monkeypatch.setattr(source, "list_input_devices", _list)
    monkeypatch.setattr(source, "_resolve_input_device", _resolve_input)
    monkeypatch.setattr(source, "_resolve_default_device", _resolve_default)

    with pytest.raises(RuntimeError, match="无可用回退设备"):
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
    source._stream = cast(Any, _FakeInputStream(fail_stop=True))
    source._mark_started()  # 伪造已启动，否则 stop() 因未启动直接返回（幂等守卫）
    subscription = source.subscribe(queue_maxsize=4)

    with pytest.raises(RuntimeError, match="stream stop failed"):
        await source.stop()

    assert source._stream is None
    assert source._loop is None
    assert source._device_info is None
    assert not source.is_started
    assert str(subscription.id) not in source._subscriptions


async def test_microphone_restart_switches_to_new_device_in_config(monkeypatch) -> None:
    """换设备后重启应切到新设备，且重启不得回写 config（回归）。

    旧 bug：_close_stream 的 finally 把当前(旧)device_info 回写进 config，
    紧接着 _resolve_input_device 读 config 时又解析回旧设备，导致换设备无效。
    现契约：设备解析结果只进运行态 _device_info，config 始终保持用户所设。
    """

    old_device = InputDeviceInfo(index=0, name="旧麦克风", max_input_channels=1, default_samplerate=48000.0, hostapi=0)
    new_device = InputDeviceInfo(index=1, name="新麦克风", max_input_channels=1, default_samplerate=48000.0, hostapi=0)
    monkeypatch.setattr(
        MicrophoneAudioStreamSource,
        "list_input_devices",
        lambda _self: _devices([old_device, new_device]),
    )
    monkeypatch.setattr(microphone_module.sd, "InputStream", lambda **_: _FakeInputStream())

    config = MicrophoneAudioStreamConfig(device_name="旧麦克风", device_index=0)
    source = MicrophoneAudioStreamSource(config)
    await source.start()
    assert source.device_info.name == "旧麦克风"

    # 模拟 GUI 换设备：设新名、清旧 index（与 stage_microphone_field 一致）
    config.device_name = "新麦克风"
    config.device_index = None

    await source.restart()

    assert source.device_info.name == "新麦克风"
    # config 保持用户所设，重启不回写（device_index 仍为用户清空后的 None）
    assert config.device_name == "新麦克风"
    assert config.device_index is None

    await source.stop()


async def _devices(items: list[InputDeviceInfo]) -> list[InputDeviceInfo]:
    return items


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


class _ReinitSource(AudioStreamSource):
    """模拟麦克风式生命周期：stop 清空状态，start 时重新解析资源。

    走 Mixin 模板方法：_do_stop 清空 _ready（模拟麦克风清 _loop/_device_info），
    _do_start 每次重新「准备」（解析设备）再启动。验证切走被 stop 复位后，再切回
    经 start 重新准备而成功——这正是简化后 switch_source 依赖的契约。
    """

    def __init__(self) -> None:
        super().__init__()
        self._ready = False
        self.start_calls = 0
        self.prepare_calls = 0

    async def _do_start(self) -> None:
        # start 自带资源准备（模拟麦克风每次启动重新解析设备）
        self._ready = True
        self.prepare_calls += 1
        self.start_calls += 1

    async def _do_stop(self) -> None:
        self._ready = False  # 模拟麦克风 stop 清空 _loop/_device_info
        self._clear_subscriptions()


async def test_router_switch_source_round_trip_reinitializes_source() -> None:
    """来回切换（mic->tts->mic）应成功：切回的源会被重新准备再 start。

    回归测试：修复前切回 mic 会因状态被 stop 清空而 RuntimeError。
    """

    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    microphone = _ReinitSource()
    tts = _ReinitSource()
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = cast(Any, tts)
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)
    router._mark_started()
    await microphone.start()
    router._forward_task = asyncio.create_task(router._forward_chunks())

    # mic -> tts
    await router.switch_source(AudioSourceKind.TTS)
    assert router.active_source_kind is AudioSourceKind.TTS
    assert tts.is_started

    # tts -> mic：切回应重新准备并成功 start（修复前此处 RuntimeError）
    await router.switch_source(AudioSourceKind.MICROPHONE)
    assert router.active_source_kind is AudioSourceKind.MICROPHONE
    assert microphone.is_started
    assert microphone.prepare_calls >= 2  # 初次 + 切回各一次
    await router.stop()


def _router_with_playback_disabled() -> AudioStreamRouter:
    """路由器 + 假麦克风 + 真 TTS,关闭 playback(避免测试开真实输出设备)。"""

    router = AudioStreamRouter()
    router.config_manager = cast(
        ConfigManager[AudioStreamRouterConfig],
        type(
            "_ConfigManager",
            (),
            {
                "config": AudioStreamRouterConfig(playback=PlaybackConfig(enabled=False)),
                "save_calls": 0,
                "save": lambda self: _save_config(self),
            },
        )(),
    )
    microphone = _DummySource()
    tts = TTSAudioStreamSource(TTSAudioStreamConfig())
    router._microphone_source = cast(MicrophoneAudioStreamSource, microphone)
    router._tts_source = tts
    router._sources = {
        AudioSourceKind.MICROPHONE: microphone,
        AudioSourceKind.TTS: tts,
    }
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = microphone.subscribe(queue_maxsize=4)
    return router


async def test_tts_source_speak_publishes_tts_chunks() -> None:
    """speak 发布的音频块带 TTS 源标识,供下游识别/过滤。"""

    tts = TTSAudioStreamSource(TTSAudioStreamConfig())
    sub = tts.subscribe(queue_maxsize=16)
    await tts.start()
    task = tts.speak("测试", duration=0.05)
    received = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
    assert received.source is AudioSourceKind.TTS
    assert received.samplerate == TTSAudioStreamConfig().samplerate
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await tts.stop()


async def test_tts_source_stop_speaking_cancels() -> None:
    """stop_speaking 取消进行中的发声任务。"""

    tts = TTSAudioStreamSource(TTSAudioStreamConfig())
    await tts.start()
    tts.speak("测试", duration=2.0)
    await asyncio.sleep(0.02)
    assert tts.is_speaking
    tts.stop_speaking()
    await asyncio.sleep(0.02)
    assert not tts.is_speaking
    await tts.stop()


async def test_router_speak_routes_tts_via_bus_takeover() -> None:
    """mic 为活动源时,speak 经总线接管把 TTS 块转发给下游(无需切活动源、不停 mic)。"""

    router = _router_with_playback_disabled()
    downstream = router.subscribe(queue_maxsize=16)
    await router.start()
    await router.speak("测试", duration=0.1)
    received = await asyncio.wait_for(downstream.queue.get(), timeout=1.0)
    assert received.source is AudioSourceKind.TTS
    await router.stop()


async def test_router_speak_restores_mic_after_utterance() -> None:
    """发声自然结束后,总线接管释放,mic 块重新流到下游。"""

    router = _router_with_playback_disabled()
    microphone = cast(_DummySource, router._microphone_source)
    downstream = router.subscribe(queue_maxsize=16)
    await router.start()
    await router.speak("测试", duration=0.05)
    await asyncio.sleep(0.2)  # 发声结束 + release 恢复 mic 转发
    while not downstream.queue.empty():  # 排空残留 TTS 块
        downstream.queue.get_nowait()
    microphone.emit(_make_chunk(0.5))
    received = await asyncio.wait_for(downstream.queue.get(), timeout=1.0)
    assert received.source is AudioSourceKind.MICROPHONE
    await router.stop()


async def test_router_stop_speaking_restores_mic_forwarding() -> None:
    """stop_speaking 取消发声后,mic 转发立即恢复。"""

    router = _router_with_playback_disabled()
    microphone = cast(_DummySource, router._microphone_source)
    downstream = router.subscribe(queue_maxsize=16)
    await router.start()
    await router.speak("测试", duration=2.0)  # 长音
    await asyncio.sleep(0.05)  # 让接管生效
    assert router.is_speaking
    router.stop_speaking()
    await asyncio.sleep(0.1)  # 让 release 恢复 mic
    assert not router.is_speaking
    while not downstream.queue.empty():  # 排空残留 TTS 块
        downstream.queue.get_nowait()
    microphone.emit(_make_chunk(0.5))
    received = await asyncio.wait_for(downstream.queue.get(), timeout=1.0)
    assert received.source is AudioSourceKind.MICROPHONE
    await router.stop()
