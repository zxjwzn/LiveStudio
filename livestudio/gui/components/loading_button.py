"""按钮忙碌态助手

异步操作期间禁用按钮并改文案,完成后复位(loading-buttons 规范)。不子类化
PushButton(其构造器为重载形式,子类化会触发类型不兼容),而是包裹一个已有按钮,
适配任意 QFluentWidgets 按钮。
"""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton


class BusyButtonController:
    """管理某个按钮的忙碌态(禁用 + 文案切换)"""

    def __init__(self, button: QAbstractButton, *, busy_text: str = "处理中…") -> None:
        self._button = button
        self._idle_text = button.text()
        self._busy_text = busy_text

    def set_busy(self, busy: bool) -> None:
        """进入/退出忙碌态"""

        self._button.setEnabled(not busy)
        self._button.setText(self._busy_text if busy else self._idle_text)
