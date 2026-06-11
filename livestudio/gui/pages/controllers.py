"""动画控制器页面。"""

from __future__ import annotations

from livestudio.gui.components.common import placeholder_page
from livestudio.gui.state import GUIState


def ControllersPage(_state: GUIState):
    return placeholder_page("动画控制器", "启停控制器", "在这里放控制器卡片和开关。")
