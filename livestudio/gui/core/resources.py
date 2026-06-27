"""GUI 资源路径与应用级图标。"""

from pathlib import Path

from PySide6.QtGui import QIcon

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
APP_ICON_PATH = _ASSETS_DIR / "app_icon.svg"


def app_icon() -> QIcon:
    """返回 LiveStudio 程序图标。"""

    return QIcon(str(APP_ICON_PATH))
