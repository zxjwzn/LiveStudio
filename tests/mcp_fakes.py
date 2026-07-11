"""MCP 测试共享桩:duck-typed app + 带一个特有 @tool 的工具集。

非测试模块(文件名不以 test_ 开头,pytest 不收集),供 test_mcp_toolset / test_mcp_server
确定性导入,避免跨测试模块导入受收集顺序影响。
"""

from __future__ import annotations

from typing import Any

from livestudio.mcp.toolset import PlatformToolset, tool
from livestudio.services.performance import PerformanceService


class _FakeHost:
    """PerformanceHost 桩:speak/emotion 自动触发 start/end 锚点,供 MCP 端到端测。"""

    def __init__(self) -> None:
        import asyncio

        self.asyncio = asyncio
        self.speaks: list[str] = []
        self.emotions: list[str] = []
        self.natives: list[tuple[str, bool]] = []
        self._speak_start = None
        self._speak_end = None
        self._emotion_start = None
        self._emotion_end = None
        self._emotion_hold_event = None

    async def launch_speak(self, text: str) -> None:
        self.speaks.append(text)
        if self._speak_start:
            self._speak_start()
        await self.asyncio.sleep(0.03)
        if self._speak_end:
            self._speak_end()

    async def stop_speak(self) -> None:
        if self._speak_end:
            self._speak_end()

    async def launch_play_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        transition_duration: float | None = None,
        hold_duration: float | None | object = ...,
    ) -> None:
        _ = (intensity, transition_duration)
        self.emotions.append(emotion)
        self._emotion_hold = hold_duration
        if self._emotion_start:
            self._emotion_start()
        if hold_duration is None:
            # 无限保持:快返回;cancel 发 end,恢复后台
            self._emotion_hold_open = True
            return
        await self.asyncio.sleep(0.02)
        if self._emotion_end:
            self._emotion_end()

    async def cancel_play_emotion(self) -> None:
        if getattr(self, "_emotion_hold_open", False):
            self._emotion_hold_open = False
            if self._emotion_end:
                self._emotion_end()
            return
        if self._emotion_end:
            self._emotion_end()

    async def launch_set_native_expression(self, name: str, active: bool) -> None:
        self.natives.append((name, active))

    async def launch_clear_native_expressions(self) -> None:
        self.natives.append(("*", False))

    def bind_speak_anchors(self, on_start, on_end):
        self._speak_start = on_start
        self._speak_end = on_end

        def _unbind() -> None:
            self._speak_start = None
            self._speak_end = None

        return _unbind

    def bind_emotion_anchors(self, on_start, on_end):
        self._emotion_start = on_start
        self._emotion_end = on_end

        def _unbind() -> None:
            self._emotion_start = None
            self._emotion_end = None

        return _unbind


# 基类固有通用动词名(connect/disconnect/待机动画/控制器/模型/情绪只读 + 时间线)。
UNIVERSAL_VERBS = {
    "connect",
    "disconnect",
    "get_current_model",
    "start_idle_animations",
    "stop_idle_animations",
    "list_controllers",
    "set_controller",
    "list_emotions",
    "add_event",
    "remove_event",
    "get_draft",
    "clear_draft",
    "enqueue_draft",
    "list_jobs",
    "get_job",
    "remove_job",
}


class _FakeApp:
    """Duck-typed app 桩:实现通用动词会调到的方法,记录调用以断言分发。"""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.played: list[str] = []
        self.play_emotion_calls: list[dict[str, object]] = []
        self.current_model: tuple[str, str] | None = ("m1", "TestModel")
        self.perf_host = _FakeHost()
        self.performance = PerformanceService(self.perf_host)

    async def connect(self) -> None:
        self.connect_calls += 1

    async def disconnect(self) -> None:
        pass

    async def start_controllers(self) -> None:
        pass

    async def stop_controllers(self) -> None:
        pass

    def list_controllers(self) -> list[Any]:
        return []

    async def set_controller(self, _name: str, running: bool) -> bool:
        return running

    def available_emotions(self) -> list[str]:
        return ["joy", "neutral"]

    def performance_add_event(
        self,
        event_type,
        params=None,
        *,
        event_id=None,
        start_anchor="group",
        start_phase="start",
        delay=0.0,
        end_anchor=None,
        end_phase="end",
        end_delay=0.0,
    ):
        return self.performance.add_event(
            event_type,
            params,
            event_id=event_id,
            start_anchor=start_anchor,
            start_phase=start_phase,
            delay=delay,
            end_anchor=end_anchor,
            end_phase=end_phase,
            end_delay=end_delay,
        ).model_dump(mode="json")

    def performance_remove_event(self, event_id: str):
        return self.performance.remove_event(event_id).model_dump(mode="json")

    def performance_get_draft(self):
        return self.performance.get_draft().model_dump(mode="json")

    def performance_clear_draft(self):
        return self.performance.clear_draft().model_dump(mode="json")

    async def performance_enqueue_draft(self, delay: float = 0.0):
        return (await self.performance.enqueue_draft(delay=delay)).model_dump(mode="json")

    def performance_list_jobs(self, *, include_finished: bool = False, limit: int = 20):
        return self.performance.list_jobs(include_finished=include_finished, limit=limit).model_dump(mode="json")

    def performance_get_job(self, job_id: str):
        snap = self.performance.get_job(job_id)
        return None if snap is None else snap.model_dump(mode="json")

    async def performance_remove_job(self, job_id=None, *, clear_all: bool = False):
        return (await self.performance.remove_job(job_id, clear_all=clear_all)).model_dump(mode="json")

    def performance_summary(self) -> str:
        return self.performance.summary_line()


class _FakeToolset(PlatformToolset[Any]):
    """带一个平台特有 @tool(ping)的测试工具集:验证通用动词(基类继承)+ 特有 分流。"""

    @property
    def platform_name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "fake platform for tests"

    async def runtime_context(self) -> str:
        return "FAKE_RUNTIME_CTX"

    @tool
    async def ping(self) -> str:
        """平台特有工具:返回固定串。"""

        return "pong"
