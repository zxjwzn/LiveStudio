"""VTube Studio 平台 MCP 工具集

表演动作(原生表情开关等)已收敛到基类时间线 add_event;本工具集仅登记平台身份。
后续若有「非时间线」的 VTS 特有能力,再在此以 @tool 声明。
"""

from __future__ import annotations

from livestudio.app.vtubestudio.app import VTubeStudioApp
from livestudio.mcp.toolset import PlatformToolset


class VTubeStudioToolset(PlatformToolset[VTubeStudioApp]):
    """VTube Studio 工具集:平台登记 + 通用动词(基类) + 时间线 add_event。"""

    @property
    def platform_name(self) -> str:
        return "vtubestudio"

    @property
    def description(self) -> str:
        return "VTube Studio 桌面 Live2D 模型控制"
