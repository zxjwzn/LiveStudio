"""把 GuiSettings 应用到 QFluentWidgets 运行时主题

设置页改动后即时调用本模块,主题/强调色立刻重绘。映射集中于此,视图层
不直接碰 setTheme/setThemeColor。
"""

from PySide6.QtGui import QColor
from qfluentwidgets import Theme, setTheme, setThemeColor

from .settings_config import GuiSettings, ThemeMode

_THEME_BY_MODE: dict[ThemeMode, Theme] = {
    ThemeMode.LIGHT: Theme.LIGHT,
    ThemeMode.DARK: Theme.DARK,
    ThemeMode.AUTO: Theme.AUTO,
}


def apply_theme(settings: GuiSettings) -> None:
    """按当前 GuiSettings 应用主题模式与强调色"""

    setTheme(_THEME_BY_MODE[settings.theme])
    setThemeColor(QColor(settings.accent_color))


def apply_all(settings: GuiSettings) -> None:
    """应用主题与强调色"""

    apply_theme(settings)
