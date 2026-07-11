"""App 侧 PerformanceHost:把 speak/emotion/原生表情接到时间线调度器"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from livestudio.services.animations.constants import EXPRESSION_CONTROLLER

if TYPE_CHECKING:
    from livestudio.app.base import BasePlatformApp


class AppPerformanceHost:
    """实现 PerformanceHost 协议:调 app 公开能力 + 绑定底层锚点。"""

    def __init__(self, app: BasePlatformApp[Any, Any]) -> None:
        self._app = app

    def _tts_source(self) -> Any:
        stream = self._app.audio_stream
        tts = getattr(stream, "tts_source", None)
        if tts is None:
            raise RuntimeError("音频路由未提供 tts_source")
        return tts

    def _expression_controller(self) -> Any | None:
        runtime = self._app.animation_manager.get_runtime(self._app.platform.name)
        return runtime.controllers.get(EXPRESSION_CONTROLLER)

    async def launch_speak(self, text: str) -> None:
        await self._app.speak(text)

    async def stop_speak(self) -> None:
        await self._app.stop_speaking()

    async def launch_play_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        transition_duration: float | None = None,
        hold_duration: float | None | object = ...,
    ) -> None:
        # hold_duration: ...=未指定(用配置); None=外部释放; float=秒数
        kwargs: dict[str, object] = {
            "intensity": intensity,
            "transition_duration": transition_duration,
        }
        if hold_duration is not ...:
            kwargs["hold_duration"] = hold_duration
        await self._app.play_emotion(emotion, **kwargs)  # type: ignore[arg-type]

    async def cancel_play_emotion(self) -> None:
        """协作结束表情 hold(幂等)。只发 release 信号,恢复由控制器后台完成。"""

        ctrl = self._expression_controller()
        if ctrl is None:
            return
        await ctrl.release_hold()

    async def launch_set_native_expression(self, name: str, active: bool) -> None:
        setter = getattr(self._app, "set_native_expression", None)
        if setter is None:
            raise RuntimeError("当前平台不支持原生表情")
        await setter(name, active)

    async def launch_clear_native_expressions(self) -> None:
        clearer = getattr(self._app, "clear_native_expressions", None)
        if clearer is None:
            raise RuntimeError("当前平台不支持原生表情")
        await clearer()

    def bind_speak_anchors(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
    ) -> Callable[[], None]:
        tts = self._tts_source()
        return tts.bind_speak_anchors(on_start, on_end)

    def bind_emotion_anchors(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
    ) -> Callable[[], None]:
        ctrl = self._expression_controller()
        if ctrl is None:
            raise RuntimeError("表情控制器未就绪")
        return ctrl.bind_emotion_anchors(on_start, on_end)
