"""GUI 资源路径与应用级图标。"""

from PySide6.QtGui import QIcon

from livestudio.gui.constants import APP_ICON_PATH


def app_icon() -> QIcon:
    """返回 LiveStudio 程序图标。"""

    return QIcon(str(APP_ICON_PATH))
