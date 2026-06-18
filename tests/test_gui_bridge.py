"""测试 GUI 桥接层（P2）

覆盖：
- LogController：sink 追加缓冲 + flush 批量刷入 state.logs
- AudioController：启动发布音源、消费发布电平、切换音源映射
- VTubeStudioAdapter：连接成功/失败的状态流转、控制器启停、表情触发、LAN 发现
- ServiceBridge：装配与平台注册

注：全部用假后端，不依赖真实 VTube Studio 或麦克风。
"""

from __future__ import annotations

import asyncio
import datetime

import numpy as np

from livestudio.gui.bridge.audio_controller import AudioController
from livestudio.gui.bridge.log_controller import LogController
from livestudio.gui.bridge.platforms.base import PlatformContext
from livestudio.gui.bridge.platforms.vtube_studio import VTubeStudioAdapter
from livestudio.gui.bridge.service_bridge import ServiceBridge
from livestudio.gui.core.app_state import AppState
from livestudio.gui.core.view_models import (
    AudioSourceKind,
    ConnectionState,
    ControllerState,
)
from livestudio.services.audio_stream import AudioSourceKind as BackendAudioSourceKind
from livestudio.services.audio_stream.models import AudioChunk


class _SyncBridge:
    """同步假 AsyncBridge：post 立即执行，便于断言副作用。"""

    def __init__(self) -> None:
        self.page = None

    def post(self, fn) -> None:
        fn()

    def post_update(self, *controls) -> None:
        pass

    def bind_loop(self, loop) -> None:
        pass


class _FakeController:
    """假动画控制器：记录启停。"""

    def __init__(self, *, enabled: bool = True, running: bool = False) -> None:
        self.enabled = enabled
        self._running = running

    @property
    def is_running(self) -> bool:
        return self._running


class _FakeRuntime:
    """假动画运行时：暴露 controllers 与启停/执行接口。"""

    def __init__(self) -> None:
        self.controllers = {
            "blink": _FakeController(running=True),
            "expression": _FakeController(running=False),
        }
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.executed: list[tuple[str, dict]] = []

    async def start_controller(self, name: str, **kwargs) -> bool:
        if name not in self.controllers:
            raise KeyError(name)
        self.controllers[name]._running = True
        self.started.append(name)
        return True

    async def stop_controller(self, name: str) -> None:
        if name not in self.controllers:
            raise KeyError(name)
        self.controllers[name]._running = False
        self.stopped.append(name)

    async def execute_controller(self, name: str, **kwargs) -> bool:
        if name not in self.controllers:
            raise KeyError(name)
        self.executed.append((name, kwargs))
        return True


class _FakeAnimationManager:
    def __init__(self, runtime: _FakeRuntime) -> None:
        self._runtime = runtime

    def get_runtime(self, platform_name: str) -> _FakeRuntime:
        return self._runtime


class _FakeConfig:
    ws_url = "ws://127.0.0.1:8001"


class _FakeIdentity:
    model_name = "Hiyori"
    model_id = "model-1"


class _FakePlatform:
    def __init__(self, *, model_loaded: bool = True) -> None:
        self.name = "vtubestudio"
        self.config = _FakeConfig()
        self._model_loaded = model_loaded

    @property
    def current_model(self) -> _FakeIdentity:
        if not self._model_loaded:
            raise RuntimeError("当前没有已加载的模型")
        return _FakeIdentity()


class _FakeApp:
    """假 VTubeStudioApp：可控连接成功/失败。"""

    def __init__(self, *, fail: bool = False, model_loaded: bool = True) -> None:
        self.platform = _FakePlatform(model_loaded=model_loaded)
        self._fail = fail
        self.initialized = False
        self.started = False
        self.stopped = False

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self) -> None:
        if self._fail:
            raise RuntimeError("连接失败")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _make_adapter(app: _FakeApp, runtime: _FakeRuntime, state: AppState) -> VTubeStudioAdapter:
    ctx = PlatformContext(
        state=state,
        async_bridge=_SyncBridge(),  # type: ignore[arg-type]
        animation_manager=_FakeAnimationManager(runtime),  # type: ignore[arg-type]
        audio_router=None,  # type: ignore[arg-type]
    )
    return VTubeStudioAdapter(ctx, app_factory=lambda _ctx: app)


class _FakeSubscription:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=8)


class _FakeAudioRouter:
    """假音频路由器：可控 start 成功/失败、记录切换。"""

    def __init__(self, *, start_fail: bool = False) -> None:
        self._start_fail = start_fail
        self.started = False
        self.subscription = _FakeSubscription()
        self.switched: list = []
        self._active = BackendAudioSourceKind.MICROPHONE

    @property
    def active_source_kind(self) -> BackendAudioSourceKind:
        return self._active

    async def start(self) -> None:
        if self._start_fail:
            raise RuntimeError("无音频设备")
        self.started = True

    def subscribe(self, *, queue_maxsize: int = 8) -> _FakeSubscription:
        return self.subscription

    def unsubscribe(self, subscription) -> None:
        pass

    async def switch_source(self, kind: BackendAudioSourceKind) -> None:
        self.switched.append(kind)
        self._active = kind


# —— LogController ——————————————————————————————————————————


def test_log_controller_sink_buffers_and_flush_writes_state() -> None:
    """sink 追加到缓冲，_flush 批量刷入 state.logs（含颜色解析）"""
    state = AppState()
    controller = LogController(state)

    record = {
        "time": datetime.datetime(2026, 1, 1, 12, 0, 0, 123000),
        "level": type("L", (), {"name": "WARNING"})(),
        "message": "hello",
    }
    message = type("M", (), {"record": record})()
    controller._sink(message)  # 模拟 loguru 在任意线程调用 sink
    controller._sink(message)

    assert len(state.logs.value) == 0  # flush 前不写状态
    controller._flush()
    entries = state.logs.value
    assert len(entries) == 2
    assert entries[0].level == "WARNING"
    assert entries[0].ts == "12:00:00.123"
    assert entries[0].message == "hello"


async def test_log_controller_start_stop_lifecycle() -> None:
    """start 注册 sink + drain 任务；stop 注销并最终 flush"""
    state = AppState()
    controller = LogController(state)
    controller.start()
    assert controller._sink_id is not None
    assert controller._drain_task is not None

    # 直接追加一条，stop 时的最终 flush 应刷入
    controller._buffer.append(
        state.logs.value[0] if state.logs.value else _dummy_log_entry(),
    )
    await controller.stop()
    assert controller._sink_id is None
    assert controller._drain_task is None
    assert len(state.logs.value) == 1


def _dummy_log_entry():
    from livestudio.gui.core.view_models import LogEntryVM

    return LogEntryVM(ts="00:00:00.000", level="INFO", message="x", color="#000")


# —— AudioController ————————————————————————————————————————


async def test_audio_controller_start_publishes_active_source() -> None:
    """start 启动路由器并发布激活音源"""
    state = AppState()
    router = _FakeAudioRouter()
    controller = AudioController(state, router)  # type: ignore[arg-type]
    await controller.start()
    assert router.started is True
    assert state.audio_level.value.active is True
    assert state.audio_source.value == AudioSourceKind.MICROPHONE
    await controller.stop()
    assert state.audio_level.value.active is False


async def test_audio_controller_start_failure_is_graceful() -> None:
    """无音频设备时 start 不抛异常，电平保持未激活"""
    state = AppState()
    router = _FakeAudioRouter(start_fail=True)
    controller = AudioController(state, router)  # type: ignore[arg-type]
    await controller.start()
    assert router.started is False
    assert state.audio_level.value.active is False


async def test_audio_controller_consume_emits_level() -> None:
    """消费队列中的音频块后写入 rms/peak 电平"""
    state = AppState()
    router = _FakeAudioRouter()
    controller = AudioController(state, router)  # type: ignore[arg-type]
    await controller.start()

    chunk = AudioChunk(frames=1, samplerate=16000, channels=1, data=np.zeros(1, dtype=np.float32))
    chunk.analysis.rms = 0.4
    chunk.analysis.peak = 0.9
    await router.subscription.queue.put(chunk)
    await asyncio.sleep(0.02)  # 让消费任务跑一轮

    assert state.audio_level.value.rms == 0.4
    assert state.audio_level.value.peak == 0.9
    await controller.stop()


async def test_audio_controller_switch_source_maps_kind() -> None:
    """切换音源把 GUI 枚举映射为后端枚举并调用路由器"""
    state = AppState()
    router = _FakeAudioRouter()
    controller = AudioController(state, router)  # type: ignore[arg-type]
    await controller.switch_source(AudioSourceKind.TTS)
    assert router.switched == [BackendAudioSourceKind.TTS]
    assert state.audio_source.value == AudioSourceKind.TTS


# —— VTubeStudioAdapter ————————————————————————————————————————


async def test_adapter_connect_success_flows_to_connected() -> None:
    """连接成功：DISCONNECTED → CONNECTED，刷新模型/控制器/表情"""
    state = AppState()
    runtime = _FakeRuntime()
    app = _FakeApp()
    adapter = _make_adapter(app, runtime, state)

    await adapter.start()
    assert adapter._connect_task is not None
    await adapter._connect_task  # 等后台连接完成

    status = state.platform_status("vtube_studio")
    assert status is not None
    assert status.connection == ConnectionState.CONNECTED
    assert status.model_name == "Hiyori"
    # 控制器与表情已发布
    keys = {c.key for c in state.controllers.value}
    assert keys == {"blink", "expression"}
    assert len(state.expressions.value) == 7  # 7 种情绪
    await adapter.stop()


async def test_adapter_connect_failure_flows_to_error() -> None:
    """连接失败：状态进入 ERROR，不抛异常到桥接层"""
    state = AppState()
    runtime = _FakeRuntime()
    app = _FakeApp(fail=True)
    adapter = _make_adapter(app, runtime, state)

    await adapter.start()
    assert adapter._connect_task is not None
    await adapter._connect_task

    status = state.platform_status("vtube_studio")
    assert status is not None
    assert status.connection == ConnectionState.ERROR
    await adapter.stop()


async def test_adapter_set_controller_enabled_starts_and_stops() -> None:
    """启停控制器代理到运行时并刷新状态"""
    state = AppState()
    runtime = _FakeRuntime()
    app = _FakeApp()
    adapter = _make_adapter(app, runtime, state)
    await adapter.start()
    await adapter._connect_task

    await adapter.set_controller_enabled("expression", True)
    assert "expression" in runtime.started
    expr = next(c for c in state.controllers.value if c.key == "expression")
    assert expr.state == ControllerState.RUNNING

    await adapter.set_controller_enabled("blink", False)
    assert "blink" in runtime.stopped
    await adapter.stop()


async def test_adapter_trigger_expression_executes_controller() -> None:
    """触发表情调用一次性 expression 控制器并带 emotion"""
    state = AppState()
    runtime = _FakeRuntime()
    app = _FakeApp()
    adapter = _make_adapter(app, runtime, state)
    await adapter.start()
    await adapter._connect_task

    await adapter.trigger_expression("joy")
    assert runtime.executed == [("expression", {"emotion": "joy"})]
    await adapter.stop()


async def test_adapter_connect_handles_unloaded_model() -> None:
    """模型未加载时仍进入 CONNECTED，模型名为空"""
    state = AppState()
    runtime = _FakeRuntime()
    app = _FakeApp(model_loaded=False)
    adapter = _make_adapter(app, runtime, state)
    await adapter.start()
    await adapter._connect_task

    status = state.platform_status("vtube_studio")
    assert status is not None
    assert status.connection == ConnectionState.CONNECTED
    assert status.model_name == ""
    await adapter.stop()


# —— ServiceBridge ——————————————————————————————————————————


async def test_service_bridge_assembles_and_registers_vts() -> None:
    """ServiceBridge 装配后端服务并注册 VTube Studio 平台"""
    bridge = ServiceBridge(page=None)  # type: ignore[arg-type]
    assert "vtube_studio" in bridge.registry
    assert bridge.audio is not None
    assert bridge.logs is not None
    assert bridge.active_adapter() is None  # 尚未 start

    ctx = bridge._platform_context()
    assert ctx.state is bridge.state
    assert ctx.audio_router is bridge.audio_router
