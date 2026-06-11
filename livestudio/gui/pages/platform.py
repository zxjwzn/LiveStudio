"""平台连接页面。"""

from __future__ import annotations

from livestudio.gui.components.common import placeholder_page
from livestudio.gui.state import GUIState


def PlatformPage(_state: GUIState):
    return placeholder_page("平台连接", "管理 VTube Studio 连接", "在这里放连接、断开、模型信息。")
