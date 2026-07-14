"""App 侧 PerformanceHost:把 speak/emotion/原生表情接到时间线调度器"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livestudio.services.animations.constants import EXPRESSION_CONTROLLER, TTS_SPEAK_CONTROLLER
from livestudio.services.performance.handle import ActionHandle, EventActionHandle

if TYPE_CHECKING:
    from livestudio.app.base import BasePlatformApp


class AppPerformanceHost:
    """实现 PerformanceHost 协议:调领域 API 并返回 ActionHandle。

    speak/emotion 均 **await 控制器 execute**(非 start 火忘),再取 current_session。
    若走 app.speak→execute_controller→start,会话尚未创建 host 会拿到 None,
    退回瞬时 Handle 导致 speak 时长为 0、队列瞬间抢跑互相打断。
    """

    def __init__(self, app: BasePlatformApp[Any, Any]) -> None:
        self._app = app

    def _tts_source(self) -> Any:
        stream = self._app.audio_stream
        tts = getattr(stream, "tts_source", None)
        if tts is None:
            raise RuntimeError("音频路由未提供 tts_source")
        return tts

    def _controller(self, name: str) -> Any | None:
        runtime = self._app.animation_manager.get_runtime(self._app.platform.name)
        return runtime.controllers.get(name)

    def _expression_controller(self) -> Any | None:
        return self._controller(EXPRESSION_CONTROLLER)

    def _ttspeak_controller(self) -> Any | None:
        return self._controller(TTS_SPEAK_CONTROLLER)

    async def launch_speak(self, text: str, *, subtitle: str | None = None) -> ActionHandle:
        ctrl = self._ttspeak_controller()
        if ctrl is None:
            raise RuntimeError("TTSpeak 控制器未就绪")
        kwargs: dict[str, object] = {"text": text}
        if subtitle is not None:
            kwargs["subtitle"] = subtitle
        # 必须 await execute:切源/字幕/tts.speak 都在其中;返回后 current_session 已挂上
        await ctrl.execute(**kwargs)
        tts = self._tts_source()
        session = getattr(tts, "current_session", None)
        if session is not None and hasattr(session, "wait_started"):
            return session  # type: ignore[return-value]
        handle = EventActionHandle()
        handle.mark_started()
        handle.mark_ended()
        return handle

    async def stop_speak(self) -> None:
        await self._app.stop_speaking()

    async def launch_play_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        transition_duration: float | None = None,
        hold_duration: float | None | object = ...,
    ) -> ActionHandle:
        ctrl = self._expression_controller()
        if ctrl is None:
            raise RuntimeError("表情控制器未就绪")
        kwargs: dict[str, object] = {
            "emotion": emotion,
            "intensity": intensity,
            "transition_duration": transition_duration,
        }
        if hold_duration is not ...:
            kwargs["hold_duration"] = hold_duration
        await ctrl.execute(**kwargs)
        session = getattr(ctrl, "current_session", None)
        if session is not None and hasattr(session, "wait_started"):
            return session  # type: ignore[return-value]
        handle = EventActionHandle()
        handle.mark_started()
        handle.mark_ended()
        return handle

    async def cancel_play_emotion(self) -> None:
        """协作结束表情 hold(幂等)。只发 release 信号,恢复由控制器后台完成。"""

        ctrl = self._expression_controller()
        if ctrl is None:
            return
        session = getattr(ctrl, "current_session", None)
        if session is not None and hasattr(session, "cancel"):
            await session.cancel()
            return
        release = getattr(ctrl, "release_hold", None)
        if release is not None:
            await release()

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
