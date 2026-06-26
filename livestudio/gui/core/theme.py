"""把 GuiSettings 应用到 QFluentWidgets 运行时主题

设置页改动后即时调用本模块,主题/强调色/字号立刻重绘。映射集中于此,视图层
不直接碰 setTheme/setThemeColor。
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
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


def _font_stylesheet(base: int) -> str:
    """构造 app 级字号样式表,仅作用于输入类控件。

    标签(FluentLabelBase 各类与 SettingCard 的裸 QLabel)一律保持 Fluent 原生字号与字重,
    不被本样式表缩放 —— 否则会出现「平台页 Fluent 标签被压成 base pt、而其他页 SettingCard
    裸 QLabel 因控件级 `font:14px` 保持 14px」的字号/粗细不一致。故这里不含任何 QLabel 选择器:
    标签字色与字号都交还 qfluentwidgets 控件级 QSS 自行按主题渲染,从而全页一致。
    """

    return f"QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{ font-size: {base}pt; }}"


def apply_font(settings: GuiSettings) -> None:
    """按当前 GuiSettings 应用界面字号(仅输入类控件;标签保持 Fluent 原生字号)。

    qfluentwidgets 各控件字号类内硬编码,app.setFont 无法覆盖,故用应用级样式表 font-size
    作用于输入控件。标签不在此缩放(见 _font_stylesheet),其字号/字色由控件级 QSS 按主题渲染。
    """

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    app.setStyleSheet(_font_stylesheet(settings.font_point_size))


def apply_all(settings: GuiSettings) -> None:
    """一次性应用主题、强调色与字号"""

    apply_theme(settings)
    apply_font(settings)
