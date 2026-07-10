"""平台运行态事件通道测试

验证 BasePlatformApp 在 connect/disconnect/start_controllers/stop_controllers/
set_controller 后广播 PlatformStateEvent。后端为单一事实源:GUI 按钮与 MCP 工具都经
这些公开方法变更态,GUI 桥接订阅事件后同步界面,使 MCP 路径不再因绕过 bridge 而让
GUI 停在旧态(诱发重复连接/重复运行)。
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from livestudio.app import VTubeStudioApp
from livestudio.app.base import (
    BasePlatformApp,
    PlatformStateEvent,
    PlatformStateKind,
)
from livestudio.services.animations import AnimationManager
from livestudio.services.animations.constants import EXPRESSION_CONTROLLER
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.platforms import PlatformService
from livestudio.services.platforms.vtubestudio import VTubeStudio


class _StubController:
    """待机控制器桩:start 受 enabled 门控(禁用时返回 False 且不改运行态),镜像真实守卫。"""

    def __init__(self, *, running: bool = False, enabled: bool = True) -> None:
        self.is_running = running
        self.enabled = enabled

    async def start(self) -> bool:
        if not self.enabled:
            return False
        self.is_running = True
        return True

    async def stop(self) -> None:
        self.is_running = False


class _StubRuntime:
    def __init__(self) -> None:
        self.controllers: dict[str, _StubController] = {}
        self.execute_kwargs: dict[str, dict[str, object]] = {}

    async def start_controller(self, name: str) -> bool:
        return await self.controllers[name].start()

    async def stop_controller(self, name: str) -> None:
        await self.controllers[name].stop()

    def get_controller(self, name: str) -> _StubController:
        return self.controllers[name]

    async def execute_controller(self, name: str, **kwargs: object) -> bool:
        self.execute_kwargs[name] = kwargs
        return True


class _StubAnimationManager:
    def __init__(self) -> None:
        self.runtime = _StubRuntime()

    def register_runtime(self, platform: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_runtime(self, _name: str) -> _StubRuntime:
        return self.runtime


class _StubPlatform:
    name = "stub"

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _StubApp(BasePlatformApp[Any, Any]):
    """最小可运行的 BasePlatformApp:钩子全为空操作,供测试事件广播。"""

    async def _subscribe_model_events(self) -> None:
        pass

    async def _load_active_model_config(self) -> None:
        pass

    async def _reload_model_config(self, model_id: str, model_name: str) -> Any:
        _ = (model_id, model_name)
        return None

    async def _apply_model_config(self, config: Any) -> None:
        _ = config


def _make_app() -> tuple[_StubApp, _StubAnimationManager, list[PlatformStateEvent]]:
    """构造 _StubApp(stub 经 cast 满足类型)并注册同步事件收集器。"""

    anim = _StubAnimationManager()
    app = _StubApp(
        platform=cast(PlatformService, _StubPlatform()),
        animation_manager=cast(AnimationManager, anim),
        audio_stream=cast(AudioStreamSource, object()),
    )
    events: list[PlatformStateEvent] = []
    app.set_state_changed_listener(events.append)
    return app, anim, events


async def test_connect_disconnect_broadcast_connected_disconnected() -> None:
    app, _anim, events = _make_app()

    await app.connect()
    await app.disconnect()

    assert [e.kind for e in events] == [
        PlatformStateKind.CONNECTED,
        PlatformStateKind.DISCONNECTED,
    ]


async def test_start_stop_controllers_broadcast_running_state() -> None:
    app, _anim, events = _make_app()

    await app.start_controllers()
    await app.stop_controllers()

    assert [e.kind for e in events] == [
        PlatformStateKind.CONTROLLERS_STARTED,
        PlatformStateKind.CONTROLLERS_STOPPED,
    ]


async def test_set_controller_broadcasts_actual_running() -> None:
    app, anim, events = _make_app()
    anim.runtime.controllers["blink"] = _StubController()

    actual = await app.set_controller("blink", True)

    assert actual is True
    assert events == [PlatformStateEvent.controller("blink", True)]


async def test_set_controller_disabled_broadcasts_not_running() -> None:
    """被禁用的控制器 start 守卫跳过(started=False),事件按真实运行态(False)广播。"""

    app, anim, events = _make_app()
    anim.runtime.controllers["blink"] = _StubController(enabled=False)

    actual = await app.set_controller("blink", True)

    assert actual is False
    assert events == [PlatformStateEvent.controller("blink", False)]


async def test_no_listener_is_safe() -> None:
    """未注册监听器时,事件广播为空操作,不抛错。"""

    app = _StubApp(
        platform=cast(PlatformService, _StubPlatform()),
        animation_manager=cast(AnimationManager, _StubAnimationManager()),
        audio_stream=cast(AudioStreamSource, object()),
    )

    await app.connect()  # 不应抛错


async def test_listener_exception_is_isolated() -> None:
    """监听器抛异常被隔离,不影响主流程(后端变更照常完成)。"""

    app = _StubApp(
        platform=cast(PlatformService, _StubPlatform()),
        animation_manager=cast(AnimationManager, _StubAnimationManager()),
        audio_stream=cast(AudioStreamSource, object()),
    )

    def _boom(_event: PlatformStateEvent) -> None:
        raise RuntimeError("listener boom")

    app.set_state_changed_listener(_boom)

    await app.connect()  # 不应抛错


async def test_async_listener_is_awaited() -> None:
    """异步监听器被 await(而非被漏掉)。"""

    app = _StubApp(
        platform=cast(PlatformService, _StubPlatform()),
        animation_manager=cast(AnimationManager, _StubAnimationManager()),
        audio_stream=cast(AudioStreamSource, object()),
    )
    seen: list[PlatformStateKind] = []

    async def _collect(event: PlatformStateEvent) -> None:
        seen.append(event.kind)

    app.set_state_changed_listener(_collect)

    await app.connect()

    assert seen == [PlatformStateKind.CONNECTED]


# --- VTubeStudio 原生表情事件(set/clear 经 _apply_native 广播 per-name 变更) ---


class _NativeStubPlatform:
    """VTubeStudioApp 原生表情测试用桩:仅提供 name 与 apply_native_expressions。"""

    name = "vtubestudio"

    async def apply_native_expressions(self, _triggers: Any, **_kwargs: Any) -> None:
        pass


def _make_vts_app() -> tuple[VTubeStudioApp, list[PlatformStateEvent]]:
    """构造 VTubeStudioApp(绕过 __init__)并注册事件收集器,供原生表情事件测试。"""

    app = object.__new__(VTubeStudioApp)
    app.platform = cast(VTubeStudio, _NativeStubPlatform())
    app._active_native = set()  # noqa: SLF001
    events: list[PlatformStateEvent] = []
    app.set_state_changed_listener(events.append)
    return app, events


async def test_set_native_expression_fires_per_name_changed() -> None:
    app, events = _make_vts_app()

    await app.set_native_expression("foo", True)
    await app.set_native_expression("bar", True)
    await app.set_native_expression("foo", False)

    assert events == [
        PlatformStateEvent.native_expression("foo", True),
        PlatformStateEvent.native_expression("bar", True),
        PlatformStateEvent.native_expression("foo", False),
    ]


async def test_clear_native_expressions_fires_per_name_false() -> None:
    app, _events = _make_vts_app()
    app._active_native = {"foo", "bar"}  # noqa: SLF001  -- 模拟已激活
    events: list[PlatformStateEvent] = []
    app.set_state_changed_listener(events.append)

    await app.clear_native_expressions()

    assert {e.kind for e in events} == {PlatformStateKind.NATIVE_EXPRESSION_CHANGED}
    assert {(e.name, e.active) for e in events} == {("foo", False), ("bar", False)}


async def test_set_native_expression_no_change_no_event() -> None:
    """重复设置相同激活态:无 diff,不广播事件(避免无谓刷新)。"""

    app, events = _make_vts_app()
    await app.set_native_expression("foo", True)
    events.clear()

    await app.set_native_expression("foo", True)  # 已激活再激活

    assert events == []


async def test_play_emotion_forwards_intensity_and_durations() -> None:
    """app.play_emotion 把 intensity/transition_duration/hold_duration 透传给 execute_controller。"""

    app, anim, _events = _make_app()
    anim.runtime.controllers[EXPRESSION_CONTROLLER] = _StubController()

    await app.play_emotion("joy", intensity=0.5, transition_duration=0.3, hold_duration=2.0)

    assert anim.runtime.execute_kwargs[EXPRESSION_CONTROLLER] == {
        "emotion": "joy",
        "intensity": 0.5,
        "transition_duration": 0.3,
        "hold_duration": 2.0,
    }


async def test_play_emotion_rejects_unknown_emotion() -> None:
    """未知情绪抛 ValueError(MCP 工具据此返回错误串)。"""

    app, _anim, _events = _make_app()

    with pytest.raises(ValueError, match="未知情绪"):
        await app.play_emotion("definitely-not-an-emotion")
