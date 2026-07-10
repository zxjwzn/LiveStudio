"""MCP 测试共享桩:duck-typed app + 带一个特有 @tool 的工具集。

非测试模块(文件名不以 test_ 开头,pytest 不收集),供 test_mcp_toolset / test_mcp_server
确定性导入,避免跨测试模块导入受收集顺序影响。
"""

from __future__ import annotations

from typing import Any

from livestudio.mcp.toolset import PlatformToolset, tool

# 基类固有的 9 个通用动词名(connect/disconnect/待机动画/控制器/模型/情绪)。
UNIVERSAL_VERBS = {
    "connect",
    "disconnect",
    "get_current_model",
    "start_idle_animations",
    "stop_idle_animations",
    "list_controllers",
    "set_controller",
    "list_emotions",
    "play_emotion",
}


class _FakeApp:
    """Duck-typed app 桩:实现通用动词会调到的方法,记录调用以断言分发。"""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.played: list[str] = []
        self.play_emotion_calls: list[dict[str, object]] = []
        self.current_model: tuple[str, str] | None = ("m1", "TestModel")

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

    async def play_emotion(
        self,
        emotion: str,
        intensity: float = 1.0,
        *,
        transition_duration: float | None = None,
        hold_duration: float | None = None,
    ) -> None:
        if emotion not in self.available_emotions():
            raise ValueError(f"未知情绪: {emotion}")
        self.played.append(emotion)
        self.play_emotion_calls.append(
            {
                "emotion": emotion,
                "intensity": intensity,
                "transition_duration": transition_duration,
                "hold_duration": hold_duration,
            }
        )


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
