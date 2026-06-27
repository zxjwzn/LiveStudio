"""VTube Studio 平台 MCP 工具集

把 VTube Studio 的能力(连接、待机动画启停、情绪解算、原生表情 toggle、模型查询)暴露为
MCP 工具。每个工具是一个 @tool 协程方法:docstring 描述语义、类型注解定入参,方法体内只调
VTubeStudioApp 的公开方法,不下探 platform / runtime 内部。

镜像 gui/bridge/vtubestudio_bridge.py 的角色,但消费者是 LLM 而非 Qt 视图。
"""

from __future__ import annotations

from livestudio.app import VTubeStudioApp

from ..toolset import PlatformToolset, tool


class VTubeStudioToolset(PlatformToolset):
    """VTube Studio 的 MCP 工具集(持有注入的 app,不构造任何后端)"""

    def __init__(self, app: VTubeStudioApp) -> None:
        self._app = app

    @property
    def platform_name(self) -> str:
        return "vtubestudio"

    @property
    def description(self) -> str:
        return "VTube Studio：控制 Live2D 模型的连接、待机动画、情绪表情解算与原生表情开关。"

    async def runtime_context(self) -> str:
        """随每次工具调用结果回给 LLM 的实时状态:当前模型 + 已激活的原生表情。

        让 LLM 每用一次工具就知道最新模型与表情态,无需额外查询(动态注入)。读的都是 app
        内存态(无 I/O、不抛错)。
        """

        model = self._app.current_model
        if model is None:
            return "未连接或未加载模型。"
        active = sorted(self._app.active_native_expressions())
        active_text = "、".join(active) if active else "无"
        return f"当前模型：{model[1]}；已激活原生表情：{active_text}。"

    # --- 连接 ---

    @tool
    async def connect(self) -> str:
        """连接 VTube Studio 并加载当前模型。

        其它工具(动画、表情)都需先连接。重复连接是安全的(幂等)。连接后可用
        get_current_model 确认已加载的模型。
        """

        await self._app.connect()
        model = self._app.current_model
        if model is None:
            return "已连接 VTube Studio，但当前未加载任何模型。"
        return f"已连接 VTube Studio，当前模型：{model[1]}。"

    @tool
    async def disconnect(self) -> str:
        """断开与 VTube Studio 的连接,并停止所有动画控制器。"""

        await self._app.disconnect()
        return "已断开 VTube Studio。"

    @tool
    async def get_current_model(self) -> dict[str, str | None]:
        """查询当前已加载的模型身份。

        返回 {model_id, model_name};未连接或未加载模型时两者为 null。
        """

        model = self._app.current_model
        if model is None:
            return {"model_id": None, "model_name": None}
        return {"model_id": model[0], "model_name": model[1]}

    # --- 待机动画控制器 ---

    @tool
    async def start_idle_animations(self) -> str:
        """启动全部已启用的待机动画(眨眼、呼吸、注视等)。需已连接并加载模型。"""

        await self._app.start_controllers()
        return "已启动待机动画。"

    @tool
    async def stop_idle_animations(self) -> str:
        """停止全部待机动画。"""

        await self._app.stop_controllers()
        return "已停止待机动画。"

    @tool
    async def list_controllers(self) -> list[dict[str, object]]:
        """列出可独立启停的待机动画控制器及其当前状态。

        返回每项含 {name, running, enabled}:name 为控制器标识(供 set_controller 使用),
        running 是否运行中,enabled 是否在模型配置中启用(禁用的无法启动)。未连接/未加载
        模型时返回空列表。
        """

        return [
            {"name": status.name, "running": status.running, "enabled": status.enabled}
            for status in self._app.list_controllers()
        ]

    @tool
    async def set_controller(self, name: str, running: bool) -> str:
        """启动或停止单个待机动画控制器(仅运行态,不改模型配置)。

        Args:
            name: 控制器标识,取自 list_controllers 返回的 name(如 "blink"/"breathing")。
            running: True 启动,False 停止。被模型配置禁用的控制器无法启动。
        """

        try:
            actual = await self._app.set_controller(name, running)
        except KeyError as exc:
            return f"控制器不存在：{name}（{exc}）"
        if running and not actual:
            return f"控制器「{name}」在模型配置中已禁用，无法启动。"
        return f"控制器「{name}」当前{'运行中' if actual else '已停止'}。"

    # --- 情绪表情解算(一次性) ---

    @tool
    async def list_emotions(self) -> list[str]:
        """列出可触发的情绪标识(如 "joy"/"anger"/"sadness"/"neutral" 等)。"""

        return self._app.available_emotions()

    @tool
    async def play_emotion(self, emotion: str) -> str:
        """触发一次情绪表情解算(过渡→保持→自动回中性)。需已连接并加载模型。

        Args:
            emotion: 情绪标识,须取自 list_emotions 的返回值。
        """

        try:
            await self._app.play_emotion(emotion)
        except ValueError as exc:
            return f"无法触发情绪：{exc}"
        except RuntimeError as exc:
            return f"无法触发情绪：{exc}"
        return f"已触发情绪：{emotion}。"

    # --- 原生表情(exp3,可激活/取消的 toggle) ---

    @tool
    async def list_native_expressions(self) -> list[str]:
        """列出当前模型可开关的原生表情(.exp3.json)名称。未加载模型时为空。"""

        return self._app.native_expressions()

    @tool
    async def set_native_expression(self, name: str, active: bool) -> str:
        """激活或取消单个原生表情(exp3 toggle)。需已连接。

        Args:
            name: 原生表情名,取自 list_native_expressions 的返回值。
            active: True 激活,False 取消。
        """

        actual = await self._app.set_native_expression(name, active)
        return f"原生表情「{name}」当前{'已激活' if actual else '未激活'}。"

    @tool
    async def clear_native_expressions(self) -> str:
        """取消所有已激活的原生表情。"""

        await self._app.clear_native_expressions()
        return "已取消全部原生表情。"
