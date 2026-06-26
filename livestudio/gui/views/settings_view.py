"""设置页:GUI 个性化(主题 / 强调色)

只暴露主题模式与强调色两项;其余字段(字号/语言/日志级别/折叠记忆)保持模型默认,不在此编辑。
改动即时生效(主题/强调色实时重绘)并回调持久化。用原生 Fluent SettingCard 行排版,
与音频页配置组件风格一致;为避免与 qconfig 绑定耦合,直接读写 GuiSettings 字段(具名属性,非 setattr)。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    ColorPickerButton,
    ComboBox,
    PrimaryPushButton,
    SettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SubtitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from livestudio.gui.core import GuiSettings, ThemeMode, apply_all

# 设置变更后回调:宿主据此持久化 GuiSettings。
SettingsChangedHandler = Callable[[GuiSettings], None]

_THEME_LABELS = [("跟随系统", ThemeMode.AUTO), ("浅色", ThemeMode.LIGHT), ("深色", ThemeMode.DARK)]


class SettingsView(QWidget):
    """GUI 偏好设置页(主题 + 强调色)"""

    def __init__(self, settings: GuiSettings, on_changed: SettingsChangedHandler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsView")
        self._settings = settings
        self._on_changed = on_changed

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = SingleDirectionScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        outer.addWidget(scroll)

        content = QWidget(scroll)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(SubtitleLabel("设置", content))

        group = SettingCardGroup("外观", content)
        self._theme_card, self._theme = self._build_theme_card(group)
        self._accent_card, self._accent = self._build_accent_card(group)
        group.addSettingCard(self._theme_card)
        group.addSettingCard(self._accent_card)
        layout.addWidget(group)
        layout.addStretch(1)

        self._reset_button = PrimaryPushButton("恢复默认", content)
        self._reset_button.setIcon(FIF.CANCEL)
        self._reset_button.clicked.connect(self._reset)
        layout.addWidget(self._reset_button)

    def _build_theme_card(self, parent: QWidget) -> tuple[SettingCard, ComboBox]:
        card = SettingCard(FIF.BRUSH, "主题模式", "浅色 / 深色 / 跟随系统", parent)
        combo = ComboBox(card)
        for label, _ in _THEME_LABELS:
            combo.addItem(label)
        combo.setCurrentIndex(self._index_of_theme(self._settings.theme))
        combo.setMinimumWidth(140)
        combo.currentIndexChanged.connect(self._apply_and_persist)
        card.hBoxLayout.addWidget(combo, 0, Qt.AlignmentFlag.AlignRight)
        card.hBoxLayout.addSpacing(16)
        return card, combo

    def _build_accent_card(self, parent: QWidget) -> tuple[SettingCard, ColorPickerButton]:
        card = SettingCard(FIF.PALETTE, "强调色", "Fluent 主题强调色", parent)
        picker = ColorPickerButton(QColor(self._settings.accent_color), "强调色", card)
        picker.colorChanged.connect(self._apply_and_persist)
        card.hBoxLayout.addWidget(picker, 0, Qt.AlignmentFlag.AlignRight)
        card.hBoxLayout.addSpacing(16)
        return card, picker

    @staticmethod
    def _index_of_theme(theme: ThemeMode) -> int:
        for index, (_, value) in enumerate(_THEME_LABELS):
            if value is theme:
                return index
        return 0

    def _collect(self) -> GuiSettings:
        # 只改主题与强调色;其余字段沿用当前设置(保持默认),避免被本页重置。
        return self._settings.model_copy(
            update={
                "theme": _THEME_LABELS[self._theme.currentIndex()][1],
                "accent_color": self._accent.color.name(),
            }
        )

    def _apply_and_persist(self) -> None:
        self._settings = self._collect()
        apply_all(self._settings)
        self._on_changed(self._settings)

    def _reset(self) -> None:
        defaults = GuiSettings()
        self._theme.setCurrentIndex(self._index_of_theme(defaults.theme))
        self._accent.setColor(QColor(defaults.accent_color))
        self._apply_and_persist()
