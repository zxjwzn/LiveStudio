"""MCP 平台工具集登记项

镜像 gui/bridge/service_bridge.py 的 PlatformRegistration:把一个平台的工具集与其登记名
成对打包,由装配点(顶层入口)用已构造的 app 实例构造工具集后注入 LiveStudioMcpServer。
server 不认识任何具体平台,新增平台只在装配点多登记一项。
"""

from __future__ import annotations

from dataclasses import dataclass

from .toolset import PlatformToolset


@dataclass(frozen=True, slots=True)
class PlatformToolsetRegistration:
    """一个平台的 MCP 登记项:登记名 + 工具集。

    name 为 switch_platform 的目标标识,须与工具集 platform_name 含义一致(由装配点保证);
    server 以登记顺序构建 list_platforms 列表。
    """

    name: str
    toolset: PlatformToolset
