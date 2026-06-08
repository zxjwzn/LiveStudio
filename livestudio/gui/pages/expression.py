"""表情测试页面。"""

from __future__ import annotations

from livestudio.gui.components.common import placeholder_page
from livestudio.gui.state import GUIState


def ExpressionPage(_state: GUIState):
    return placeholder_page("表情测试", "预览和触发表情", "在这里放情绪滑块、意图下拉、预览结果。")
