"""测试 speak/stop_speaking 经 TTSpeak 控制器触发(不再直连 tts_source)

回归:此前 app.speak 自行读控制器配置 + 切源 + 直调 tts_source.speak,绕过
TTSpeakController.execute;现统一改为 runtime.execute_controller/stop_controller,
控制器成为唯一发声入口。本测试用桩 runtime 验证委派契约(控制器内部行为见
test_tts_speak_controller.py)。
"""

# ruff: noqa: SLF001

from __future__ import annotations

from typing import Any, cast

import pytest

from livestudio.app.base import BasePlatformApp
from livestudio.services.animations import AnimationManager
from livestudio.services.animations.constants import TTS_SPEAK_CONTROLLER
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.platforms import PlatformService


class _Platform:
    name = "stub"


class _RecRuntime:
    """记录 execute_controller/stop_controller 调用,不做真实控制器副作用。"""

    def __init__(self) -> None:
        self.controllers: dict[str, Any] = {TTS_SPEAK_CONTROLLER: object()}
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.stopped: list[str] = []

    async def execute_controller(self, name: str, **kwargs: object) -> bool:
        self.executed.append((name, dict(kwargs)))
        return True

    async def stop_controller(self, name: str) -> None:
        self.stopped.append(name)


class _RecAnimManager:
    def __init__(self) -> None:
        self.runtime = _RecRuntime()

    def register_runtime(self, _platform: Any) -> None:
        pass

    def get_runtime(self, _name: str) -> _RecRuntime:
        return self.runtime


class _StubApp(BasePlatformApp[Any, Any]):
    """最小可运行的 BasePlatformApp:钩子全为空操作,仅供测 speak 委派。"""

    async def _subscribe_model_events(self) -> None:
        pass

    async def _load_active_model_config(self) -> None:
        pass

    async def _reload_model_config(self, model_id: str, model_name: str) -> Any:
        _ = (model_id, model_name)
        return None

    async def _apply_model_config(self, config: Any) -> None:
        _ = config


def _make_app() -> tuple[_StubApp, _RecRuntime]:
    anim = _RecAnimManager()
    app = _StubApp(
        platform=cast(PlatformService, _Platform()),
        animation_manager=cast(AnimationManager, anim),
        audio_stream=cast(AudioStreamSource, object()),
    )
    return app, anim.runtime


async def test_speak_delegates_to_ttspeak_controller() -> None:
    """app.speak -> runtime.execute_controller(TTS_SPEAK_CONTROLLER, text=...)"""

    app, runtime = _make_app()
    await app.speak("你好")
    assert runtime.executed == [(TTS_SPEAK_CONTROLLER, {"text": "你好"})]


async def test_speak_strips_text_and_forwards_opts() -> None:
    """文本去空白;opts(model 等)透传给控制器 execute。"""

    app, runtime = _make_app()
    await app.speak("  hi  ", model="s2.1-pro")  # type: ignore[call-arg]
    assert runtime.executed == [(TTS_SPEAK_CONTROLLER, {"text": "hi", "model": "s2.1-pro"})]


async def test_speak_empty_raises() -> None:
    app, _ = _make_app()
    with pytest.raises(ValueError):
        await app.speak("")


async def test_speak_non_str_raises() -> None:
    app, _ = _make_app()
    with pytest.raises(TypeError):
        await app.speak(123)  # type: ignore[arg-type]


async def test_speak_without_controller_raises() -> None:
    """未加载模型(无 tts_speak 控制器)时给出可操作错误。"""

    app, runtime = _make_app()
    runtime.controllers.clear()
    with pytest.raises(RuntimeError, match="TTSpeak 控制器未就绪"):
        await app.speak("hi")
    assert runtime.executed == []


async def test_stop_speaking_delegates_to_controller() -> None:
    """app.stop_speaking -> runtime.stop_controller(TTS_SPEAK_CONTROLLER)"""

    app, runtime = _make_app()
    await app.stop_speaking()
    assert runtime.stopped == [TTS_SPEAK_CONTROLLER]


async def test_stop_speaking_without_controller_is_noop() -> None:
    """无控制器时停止为幂等空操作(不抛错)。"""

    app, runtime = _make_app()
    runtime.controllers.clear()
    await app.stop_speaking()
    assert runtime.stopped == []
