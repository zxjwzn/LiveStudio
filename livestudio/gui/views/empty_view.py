"""空白占位页

仪表盘 / 平台页已移除,导航项仍保留但内容为空。后续重建时替换为真实页面。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class EmptyView(QWidget):
    """空白页(仅占位,无内容)"""

    def __init__(self, object_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
