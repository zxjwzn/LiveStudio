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
from livestudio.services.audio_stream.sources.tts import tts as tts_module
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.services.audio_stream.sources.tts.engines import TtsAudioOutput
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


async def test_tts_restart_preserves_subscriptions() -> None:
    """TTS 源软重启保留订阅:重启后块仍能到下游(回归:重载后 speak 无反应)"""

    source = TTSAudioStreamSource(TTSAudioStreamConfig())
    subscription = source.subscribe(queue_maxsize=16)
    await source.start()

    # 重启前能收到静音块
    chunk = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert chunk.source is AudioSourceKind.TTS

    await source.restart()  # 软重启(不应清订阅)

    # 重启后仍能收到块(订阅存活);若 _do_restart 清了订阅,这里会超时
    chunk_after = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert chunk_after.source is AudioSourceKind.TTS

    await source.stop()


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
    router.config.playback.enabled = False  # 关音频播放,避免测试开真实输出流
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


class _FakeEngine:
    """假引擎(duck-typed):按预定 outputs 产出,用于测 TTS 源 speak 分发"""

    def __init__(self, outputs, *, sample_rate: int = 24000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._outputs = list(outputs)

    async def synthesize(self, _text: str, **_opts: object):
        for output in self._outputs:
            yield output


class _SlowEngine:
    """假引擎(duck-typed):阻塞,用于测取消"""

    def __init__(self, *, sample_rate: int = 24000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels

    async def synthesize(self, _text: str, **_opts: object):
        await asyncio.sleep(10)
        yield TtsAudioOutput(data=np.zeros((1, 1), dtype=np.float32), frames=1)


class _ImmediateYieldEngine:
    """立即 yield 一帧的引擎;用 async with 持有资源,__aexit__ 里 await(模拟 httpx
    ``response.aclose`` 的网络清理),并仅在 await 完成后标记 closed。

    配合 monkeypatch _enqueue_audio 阻塞,可使 _synthesize 停在循环体(生成器停在 yield),
    复现「取消命中循环体」的真实 bug 场景。closed=True 表示异步清理完整完成(而非被取消打断)。
    """

    def __init__(self, *, sample_rate: int = 24000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.closed = False

    async def synthesize(self, _text: str, **_opts: object):
        class _Resource:
            def __init__(self, owner: _ImmediateYieldEngine) -> None:
                self._owner = owner

            async def __aenter__(self) -> _Resource:  # noqa: PYI034
                return self

            async def __aexit__(self, *_exc: object) -> None:
                await asyncio.sleep(0.01)  # 模拟 httpx aclose 的网络清理 await
                self._owner.closed = True

        async with _Resource(self):
            yield TtsAudioOutput(data=np.zeros((400, 1), dtype=np.float32), frames=400)
            await asyncio.sleep(10)





async def test_synth_async_generator_closed_on_cancel(monkeypatch) -> None:
    """取消命中循环体(生成器停在 yield)时,aclosing 显式 aclose 引擎异步生成器。

    回归:旧实现 ``async for`` 不 aclose;新 speak/stop 取消 _synthesize 时,若取消命中
    ``await self._enqueue_audio(frame)``(循环体内),生成器滞留在 yield,留给 GC 在另一任务
    跑 aclose,触发「async generator ignored GeneratorExit」与 anyio「cancel scope 跨任务」。
    本测试用阻塞的 _enqueue_audio 把生成器固定在 yield,再取消,验证 aclose 被显式调用。
    """

    engines: list[_ImmediateYieldEngine] = []

    def _make(_kind: object, _conn: object, **_kw: object) -> _ImmediateYieldEngine:
        engine = _ImmediateYieldEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(tts_module, "make_engine", _make)

    # 阻塞 _enqueue_audio:生成器 yield 后 _synthesize 停在循环体,生成器停在 yield
    blocked = asyncio.Event()

    async def _blocking_enqueue(_self: TTSAudioStreamSource, _data: object) -> None:
        await blocked.wait()

    monkeypatch.setattr(TTSAudioStreamSource, "_enqueue_audio", _blocking_enqueue)

    source = TTSAudioStreamSource(TTSAudioStreamConfig())
    await source.start()
    speak_start = len(engines)  # lazy:__init__ 不再预建引擎,speak 前列表为空

    await source.speak("first")
    await asyncio.sleep(0.02)  # _synthesize 进入 _enqueue_audio 阻塞(生成器停在 yield)

    first = engines[speak_start]
    assert source.is_speaking
    assert not first.closed

    synth = source._synth_task
    assert synth is not None and not synth.done()
    synth.cancel()  # 取消命中循环体(生成器停在 yield),复现真实 bug 场景
    with contextlib.suppress(asyncio.CancelledError):
        await synth

    assert first.closed, "被取消的引擎异步生成器必须显式 aclose(而非留给 GC)"
    blocked.set()  # 释放 _enqueue_audio(任务已取消,仅做清理)
    await source.stop()


async def test_tts_stop_speaking_invokes_on_interrupt(monkeypatch) -> None:
    """stop_speaking / 新 speak 调用 on_interrupt 冲刷播放残留"""

    monkeypatch.setattr(tts_module, "make_engine", lambda _kind, _conn, **kw: _SlowEngine(**kw))
    calls: list[int] = []
    source = TTSAudioStreamSource(
        TTSAudioStreamConfig(),
        on_interrupt=lambda: calls.append(1),
    )
    await source.start()
    await source.speak("hi")  # speak 内部先 stop_speaking → flush 一次
    await asyncio.sleep(0.02)
    assert calls == [1]
    await source.stop_speaking()
    assert calls == [1, 1]
    await source.stop_speaking()
    assert calls == [1, 1, 1]
    await source.stop()


async def test_tts_speak_calls_on_prepare(monkeypatch) -> None:
    """speak 在首包上总线前 await on_prepare(打开播放设备)"""

    monkeypatch.setattr(tts_module, "make_engine", lambda _kind, _conn, **kw: _SlowEngine(**kw))
    order: list[str] = []

    async def _prepare() -> None:
        order.append("prepare")

    source = TTSAudioStreamSource(
        TTSAudioStreamConfig(),
        on_prepare=_prepare,
        on_interrupt=lambda: order.append("interrupt"),
    )
    await source.start()
    await source.speak("hi")
    await asyncio.sleep(0.02)
    # stop_speaking(无任务) → interrupt; prepare; 启动合成
    assert order[0] == "interrupt"
    assert "prepare" in order
    assert order.index("prepare") > order.index("interrupt")
    await source.stop_speaking()
    await source.stop()


async def test_tts_present_clock_feeds_bus_at_frame_rate(monkeypatch) -> None:
    """大引擎块经呈现时钟切帧上总线:sleep 期间总线持续有块(嘴型同源)"""

    frames = 24000  # 1s @24k
    outputs = [TtsAudioOutput(data=np.full((frames, 1), 0.3, dtype=np.float32), frames=frames)]
    monkeypatch.setattr(
        tts_module,
        "make_engine",
        lambda _kind, _conn, **_kw: _FakeEngine(outputs, sample_rate=24000, channels=1),
    )
    source = TTSAudioStreamSource(TTSAudioStreamConfig(samplerate=24000))
    sub = source.subscribe(queue_maxsize=256)
    await source.start()
    await asyncio.sleep(0.02)
    while not sub.queue.empty():
        sub.queue.get_nowait()

    await source.speak("feed")
    got = 0
    deadline = asyncio.get_running_loop().time() + 0.5
    while asyncio.get_running_loop().time() < deadline:
        try:
            chunk = await asyncio.wait_for(sub.queue.get(), timeout=0.08)
        except TimeoutError:
            break
        if float(np.max(np.abs(chunk.data))) > 0.0:
            got += 1
            # 每帧约 1/60s @24k = 400 samples
            assert chunk.frames <= 400 + 1
    assert got >= 10, f"expected continuous present-clock chunks, got {got}"
    await source.stop_speaking()
    await source.stop()


async def test_tts_present_does_not_burst_whole_utterance(monkeypatch) -> None:
    """呈现时钟不会把 1s 音频在 0.1s 内全部塞进总线"""

    frames = 24000
    outputs = [TtsAudioOutput(data=np.full((frames, 1), 0.2, dtype=np.float32), frames=frames)]
    monkeypatch.setattr(
        tts_module,
        "make_engine",
        lambda _kind, _conn, **_kw: _FakeEngine(outputs, sample_rate=24000, channels=1),
    )
    source = TTSAudioStreamSource(TTSAudioStreamConfig(samplerate=24000))
    sub = source.subscribe(queue_maxsize=256)
    await source.start()
    await asyncio.sleep(0.02)
    while not sub.queue.empty():
        sub.queue.get_nowait()

    await source.speak("pace")
    await asyncio.sleep(0.15)
    non_silent = 0
    while not sub.queue.empty():
        chunk = sub.queue.get_nowait()
        if float(np.max(np.abs(chunk.data))) > 0.0:
            non_silent += 1
    # 0.15s * 60fps ≈ 9 帧,允许抖动;绝不是 60 帧整秒
    assert 4 <= non_silent <= 20
    await source.stop_speaking()
    await source.stop()

async def test_speak_session_starts_on_first_engine_pcm_not_silence(monkeypatch) -> None:
    """SpeakSession.started 在引擎 PCM 上总线时才置位,合成前静音占位不算。"""

    gate = asyncio.Event()
    frames = 800  # 两帧 @24k/60

    class _GatedEngine:
        def __init__(self, *, sample_rate: int = 24000, channels: int = 1) -> None:
            self.sample_rate = sample_rate
            self.channels = channels

        async def synthesize(self, _text: str, **_opts: object):
            await gate.wait()
            data = np.full((frames, 1), 0.4, dtype=np.float32)
            yield TtsAudioOutput(data=data, frames=frames)

    monkeypatch.setattr(
        tts_module,
        "make_engine",
        lambda _kind, _conn, **kw: _GatedEngine(**kw),
    )
    source = TTSAudioStreamSource(TTSAudioStreamConfig(samplerate=24000))
    await source.start()
    session = await source.speak("gate")
    # present 会先推静音占位,但 started 仍应 false
    await asyncio.sleep(0.08)
    assert not session.started
    gate.set()
    await asyncio.wait_for(session.wait_started(), timeout=1.0)
    assert session.started
    await source.stop_speaking()
    await source.stop()
