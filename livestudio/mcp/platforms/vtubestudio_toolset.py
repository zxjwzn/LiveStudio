"""VTube Studio 平台 MCP 工具集

把 VTube Studio 的平台特有能力(原生表情 toggle、平台实时状态)暴露为 MCP 工具。平台无关的
通用动词(connect / 情绪 / 控制器等)已在 PlatformToolset 基类以 @tool(builtin=True) 固有化,
本子类只补 VTS 特有工具与 runtime_context 覆盖,方法体内只调 VTubeStudioApp 公开方法,不下探
platform / runtime 内部。

镜像 gui/bridge/vtubestudio_bridge.py 的角色,但消费者是 LLM 而非 Qt 视图。
"""

from __future__ import annotations

from livestudio.app import VTubeStudioApp

from ..toolset import PlatformToolset, tool


class VTubeStudioToolset(PlatformToolset[VTubeStudioApp]):
    """VTube Studio 的 MCP 工具集(持有注入的 app,不构造任何后端)"""

    def __init__(self, app: VTubeStudioApp) -> None:
        super().__init__(app)

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

    # --- 原生表情(exp3,可激活/取消的 toggle;VTS 特有) ---

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
