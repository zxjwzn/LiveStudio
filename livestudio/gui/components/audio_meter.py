"""实时音频电平表:RMS / Peak 双条 + overflow 提示

自绘 QWidget,只按最新电平重绘两条进度条与数值(不触发布局重排)。compact 用于仪表盘,
large 用于音频页,仅尺寸参数不同。颜色按电平绿→黄,overflow 红(00 §3.1)。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import isDarkTheme, qconfig, themeColor

from livestudio.gui.core import colors

_BAR_GAP = 6
_LABEL_WIDTH = 48

# 轨道(未填充)与文字色按主题切换:暗色用深轨道+浅字,亮色用浅轨道+深字
_TRACK_DARK = "#1E293B"
_TRACK_LIGHT = "#E2E8F0"
_TEXT_DARK = "#F8FAFC"
_TEXT_LIGHT = "#0F172A"


def _level_color(level: float, overflowed: bool) -> QColor:
    # 正常电平用 GUI 强调色(themeColor),随设置页改色而变;临近峰值/溢出仍保留
    # 黄/红警示语义,确保危险信号不被强调色淹没。
    if overflowed:
        return QColor(colors.ERROR)
    if level >= 0.85:
        return QColor(colors.WARNING)
    return themeColor()


class AudioMeter(QWidget):
    """RMS + Peak 双条电平表"""

    def __init__(self, *, large: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rms = 0.0
        self._peak = 0.0
        self._overflowed = False
        self._bar_height = 22 if large else 12
        height = self._bar_height * 2 + _BAR_GAP + 8
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 主题切换时重绘,使轨道/文字色跟随明暗
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.update()

    def set_level(self, rms: float, peak: float, overflowed: bool) -> None:
        """更新电平并重绘(值域 [0,1],外部已保证)"""

        self._rms = max(0.0, min(1.0, rms))
        self._peak = max(0.0, min(1.0, peak))
        self._overflowed = overflowed
        self.update()

    def paintEvent(self, event: object) -> None:
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = isDarkTheme()
        track = QColor(_TRACK_DARK if dark else _TRACK_LIGHT)
        text = QColor(_TEXT_DARK if dark else _TEXT_LIGHT)

        bar_width = self.width() - _LABEL_WIDTH
        self._draw_bar(painter, 4, bar_width, self._rms, "RMS", track, text)
        self._draw_bar(painter, 4 + self._bar_height + _BAR_GAP, bar_width, self._peak, "PEAK", track, text)
        painter.end()

    def _draw_bar(
        self,
        painter: QPainter,
        y: int,
        width: int,
        level: float,
        label: str,
        track: QColor,
        text: QColor,
    ) -> None:
        painter.setPen(text)
        painter.drawText(0, y, _LABEL_WIDTH - 6, self._bar_height, Qt.AlignmentFlag.AlignVCenter, label)

        x = _LABEL_WIDTH
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(x, y, width, self._bar_height, 4, 4)

        filled = int(width * level)
        if filled > 0:
            painter.setBrush(_level_color(level, self._overflowed))
            painter.drawRoundedRect(x, y, filled, self._bar_height, 4, 4)
