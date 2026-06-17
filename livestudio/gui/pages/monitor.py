"""监控页面。"""

from livestudio.gui.components.common import placeholder_page
from livestudio.gui.state import GUIState


def MonitorPage(_state: GUIState):
    return placeholder_page("实时监控", "系统运行状态总览", "在这里放音频电平、平台状态、控制器状态。")
