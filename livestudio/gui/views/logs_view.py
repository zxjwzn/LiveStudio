"""日志页:实时日志表 + 级别过滤 + 搜索 + 清空

订阅 LogController.logEmitted,逐条入表;级别多选与搜索框做视图侧过滤;条目数设上限
防止无限增长。级别用语义色 + 图标双编码。
"""

from __future__ import annotations

from collections import deque

from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    CheckBox,
    InfoBar,
    InfoBarPosition,
    PushButton,
    SearchLineEdit,
    SubtitleLabel,
    TableWidget,
    isDarkTheme,
    qconfig,
)

from livestudio.gui.bridge import LogController, LogEntry
from livestudio.gui.constants import LOG_LEVEL_COLOR_DARK, LOG_LEVEL_COLOR_LIGHT, LOG_LEVELS, LOG_MAX_ROWS
from livestudio.gui.core import colors


def _level_color(level: str) -> QColor:
    table = LOG_LEVEL_COLOR_DARK if isDarkTheme() else LOG_LEVEL_COLOR_LIGHT
    return QColor(table.get(level, colors.TEXT))


class LogsView(QWidget):
    """日志查看页"""

    def __init__(self, logs: LogController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logsView")
        self._entries: deque[LogEntry] = deque(maxlen=LOG_MAX_ROWS)
        self._level_filters: dict[str, CheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("日志", self))

        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        for level in LOG_LEVELS:
            box = CheckBox(level, controls)
            box.setChecked(True)
            box.stateChanged.connect(self._refilter)
            self._level_filters[level] = box
            controls_layout.addWidget(box)
        controls_layout.addStretch(1)

        self._auto_scroll = CheckBox("自动滚动", controls)
        self._auto_scroll.setChecked(True)
        controls_layout.addWidget(self._auto_scroll)

        self._search = SearchLineEdit(controls)
        self._search.setPlaceholderText("搜索日志…")
        self._search.textChanged.connect(self._refilter)
        controls_layout.addWidget(self._search)

        self._clear_button = PushButton("清空", controls)
        self._clear_button.clicked.connect(self._clear)
        controls_layout.addWidget(self._clear_button)

        self._copy_button = PushButton("复制选中", controls)
        self._copy_button.clicked.connect(self._copy_selected)
        controls_layout.addWidget(self._copy_button)
        layout.addWidget(controls)

        self._table = TableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["时间", "级别", "来源", "消息"])
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, 1)

        logs.logEmitted.connect(self._append)
        # 切换明/暗主题时重染级别列,避免旧行沿用上一主题的颜色看不清
        qconfig.themeChanged.connect(self._recolor_levels)

    def _recolor_levels(self) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item is not None:
                item.setForeground(_level_color(item.text()))

    def _append(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self._passes_filter(entry):
            self._add_row(entry)
            self._trim_rows()

    def _add_row(self, entry: LogEntry) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        items = [
            QTableWidgetItem(entry.timestamp),
            QTableWidgetItem(entry.level),
            QTableWidgetItem(entry.source),
            QTableWidgetItem(entry.message),
        ]
        color = _level_color(entry.level)
        items[1].setForeground(color)
        for column, item in enumerate(items):
            self._table.setItem(row, column, item)
        if self._auto_scroll.isChecked():
            self._table.scrollToBottom()

    def _trim_rows(self) -> None:
        while self._table.rowCount() > LOG_MAX_ROWS:
            self._table.removeRow(0)

    def _passes_filter(self, entry: LogEntry) -> bool:
        box = self._level_filters.get(entry.level)
        if box is not None and not box.isChecked():
            return False
        keyword = self._search.text().strip().lower()
        return not (keyword and keyword not in entry.message.lower() and keyword not in entry.source.lower())

    def _refilter(self) -> None:
        self._table.setRowCount(0)
        for entry in self._entries:
            if self._passes_filter(entry):
                self._add_row(entry)

    def _clear(self) -> None:
        self._entries.clear()
        self._table.setRowCount(0)

    def _copy_selected(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        if not rows:
            return

        lines: list[str] = []
        for row in rows:
            values = []
            for column in range(self._table.columnCount()):
                item = self._table.item(row, column)
                values.append(item.text() if item is not None else "")
            lines.append("\t".join(values))
        QGuiApplication.clipboard().setText("\n".join(lines))
        InfoBar.success(
            "已复制",
            f"已复制 {len(lines)} 条日志",
            duration=2000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
