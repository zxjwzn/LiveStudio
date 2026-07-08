"""GUI core 常量"""

from typing import Final

from qfluentwidgets import Theme

from .settings_config import ThemeMode

GUI_SETTINGS_FILENAME: Final[str] = "gui.yaml"
THEME_BY_MODE: Final[dict[ThemeMode, Theme]] = {
    ThemeMode.LIGHT: Theme.LIGHT,
    ThemeMode.DARK: Theme.DARK,
    ThemeMode.AUTO: Theme.AUTO,
}
THEME_LABELS: Final[list[tuple[str, ThemeMode]]] = [
    ("跟随系统", ThemeMode.AUTO),
    ("浅色", ThemeMode.LIGHT),
    ("深色", ThemeMode.DARK),
]
