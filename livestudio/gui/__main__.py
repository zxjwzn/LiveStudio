"""GUI 入口:python -m livestudio.gui

搭起 QApplication 与 qasync 事件循环,让 Qt 与项目既有 asyncio 后端共存,再把
控制权交给 GuiApplication.run()。
"""

import sys

import qasync
from PySide6.QtWidgets import QApplication

from livestudio.gui.app import GuiApplication
from livestudio.gui.core.async_utils import silence_proactor_connection_reset_on_close
from livestudio.gui.core.resources import app_icon


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LiveStudio")
    app.setWindowIcon(app_icon())

    event_loop = qasync.QEventLoop(app)
    # 屏蔽 Windows proactor 套接字拆除时的良性 ConnectionResetError 噪音(停机收回 MCP
    # 客户端长连等场景会刷屏;源于平台层,非项目代码)。
    silence_proactor_connection_reset_on_close(event_loop)

    gui_app = GuiApplication()
    with event_loop:
        event_loop.run_until_complete(gui_app.run())


if __name__ == "__main__":
    main()
