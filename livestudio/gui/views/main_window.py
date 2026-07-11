"""主窗口:FluentWindow + 侧边导航

注册 7 个一级页面(仪表盘/平台/音频/字幕/音频播放/日志置顶,设置置底)。关闭窗口时不立刻退出,
而是回调 GuiApplication 触发后端有序停机,停机完成后再真正退出 —— 避免 qasync
事件循环在后端任务进行中被销毁。
"""

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentWindow, NavigationItemPosition

from livestudio.gui.core import icons
from livestudio.gui.core.resources import app_icon

# 关闭请求回调:窗口把「用户想关闭」上报给 GuiApplication,由后者编排异步停机。
CloseRequestHandler = Callable[[], None]


class MainWindow(FluentWindow):
    """LiveStudio 主窗口"""

    def __init__(
        self,
        *,
        dashboard: QWidget,
        platform: QWidget,
        audio: QWidget,
        subtitle: QWidget,
        playback: QWidget,
        logs: QWidget,
        mcp: QWidget,
        settings: QWidget,
    ) -> None:
        super().__init__()
        self.setWindowTitle("LiveStudio")
        self.setWindowIcon(app_icon())
        self.setMicaEffectEnabled(False)
        self.setMinimumSize(960, 640)
        self.resize(1100, 720)

        self._close_requested = False
        self._on_close_request: CloseRequestHandler | None = None

        self.addSubInterface(dashboard, icons.NAV_DASHBOARD, "仪表盘")
        self.addSubInterface(platform, icons.NAV_PLATFORM, "平台")
        self.addSubInterface(audio, icons.NAV_AUDIO, "音频")
        self.addSubInterface(subtitle, icons.NAV_SUBTITLE, "字幕")
        self.addSubInterface(playback, icons.NAV_PLAYBACK, "音频播放")
        self.addSubInterface(logs, icons.NAV_LOGS, "日志")
        self.addSubInterface(mcp, icons.NAV_MCP, "MCP")
        self.addSubInterface(
            settings,
            icons.NAV_SETTINGS,
            "设置",
            position=NavigationItemPosition.BOTTOM,
        )

    def set_close_request_handler(self, handler: CloseRequestHandler) -> None:
        """注册关闭请求处理器(由 GuiApplication 编排异步停机)"""

        self._on_close_request = handler

    def confirm_close(self) -> None:
        """停机完成后由 GuiApplication 调用,放行真正的关闭"""

        self._close_requested = True
        self.close()

    def closeEvent(self, e: QCloseEvent) -> None:
        if self._close_requested or self._on_close_request is None:
            super().closeEvent(e)
            return
        # 首次关闭:拦截,转交异步停机;停机完成后 confirm_close 再次进入并放行。
        e.ignore()
        self._on_close_request()
