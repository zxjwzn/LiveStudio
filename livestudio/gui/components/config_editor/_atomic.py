"""标量字段编辑器:bool / int / float / str / path

每个字段渲染为 Fluent SettingCard 横条(左图标 + 标题 + 副标题 + 右对齐控件)。
bare 模式(被 Optional/Union/List 复用)只渲染控件、不画卡片,避免卡中套卡。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import DoubleSpinBox, LineEdit, PushButton, SettingCard, SpinBox, SwitchButton

from ._base import FieldEditor
from ._schema_types import FieldSpec, resolve_icon
from .constants import ERROR_COLOR, FLOAT_MAX, FLOAT_MIN, INT_MAX, INT_MIN


class _CardEditor(FieldEditor):
    """SettingCard 横条编辑器骨架:子类只负责构造控件并调用 _mount。

    - 非 bare:建 SettingCard(图标+标题+副标题),控件右对齐挂载;错误显示为副标题变红。
    - bare:不画卡片,只用瘦水平布局装控件;错误回退为 tooltip,由外层容器卡呈现。
    """

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._card: SettingCard | None = None
        self._default_content = spec.description or ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        if spec.bare:
            self._row = QHBoxLayout()
            self._row.setContentsMargins(0, 0, 0, 0)
            self._row.setSpacing(8)
            outer.addLayout(self._row)
        else:
            self._card = SettingCard(resolve_icon(spec.icon), spec.label, spec.description or None, self)
            outer.addWidget(self._card)

    def _mount(self, control: QWidget) -> None:
        control.setEnabled(not self.spec.readonly)
        if self._card is not None:
            self._card.hBoxLayout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight)
            self._card.hBoxLayout.addSpacing(16)
        else:
            self._row.addWidget(control, 1)

    def set_error(self, message: str | None) -> None:
        if self._card is None:
            self.setToolTip(message or "")
            return
        if message:
            self._card.setContent(message)
            self._card.contentLabel.setStyleSheet(f"color: {ERROR_COLOR};")
        else:
            # contentLabel 是裸 QLabel,字色由 SettingCard 全局 QSS 按主题控制;清空内联样式即回到跟随主题
            self._card.contentLabel.setStyleSheet("")
            self._card.setContent(self._default_content)


class BoolEditor(_CardEditor):
    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._switch = SwitchButton(self)
        self._switch.setOnText("开")
        self._switch.setOffText("关")
        self._switch.checkedChanged.connect(lambda _: self.valueChanged.emit())
        self._mount(self._switch)

    def get_value(self) -> Any:
        return self._switch.isChecked()

    def set_value(self, value: Any) -> None:
        self._switch.setChecked(bool(value))


class IntEditor(_CardEditor):
    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._spin = SpinBox(self)
        self._spin.setMinimumWidth(140)
        self._spin.setRange(
            int(spec.minimum) if spec.minimum is not None else INT_MIN,
            int(spec.maximum) if spec.maximum is not None else INT_MAX,
        )
        self._spin.valueChanged.connect(lambda _: self.valueChanged.emit())
        self._mount(self._spin)

    def get_value(self) -> Any:
        return self._spin.value()

    def set_value(self, value: Any) -> None:
        if value is not None:
            self._spin.setValue(int(value))


class FloatEditor(_CardEditor):
    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._spin = DoubleSpinBox(self)
        self._spin.setMinimumWidth(140)
        self._spin.setDecimals(4)
        self._spin.setRange(
            spec.minimum if spec.minimum is not None else FLOAT_MIN,
            spec.maximum if spec.maximum is not None else FLOAT_MAX,
        )
        self._spin.valueChanged.connect(lambda _: self.valueChanged.emit())
        self._mount(self._spin)

    def get_value(self) -> Any:
        return self._spin.value()

    def set_value(self, value: Any) -> None:
        if value is not None:
            self._spin.setValue(float(value))


class StrEditor(_CardEditor):
    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._edit = LineEdit(self)
        self._edit.setMinimumWidth(220)
        self._edit.textChanged.connect(lambda _: self.valueChanged.emit())
        self._mount(self._edit)

    def get_value(self) -> Any:
        return self._edit.text()

    def set_value(self, value: Any) -> None:
        self._edit.setText("" if value is None else str(value))


class PathEditor(_CardEditor):
    """文本框 + 浏览按钮(整体右挂)"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        self._edit = LineEdit(row)
        self._edit.setMinimumWidth(220)
        self._edit.textChanged.connect(lambda _: self.valueChanged.emit())
        row_layout.addWidget(self._edit, 1)

        self._browse = PushButton("浏览", row)
        self._browse.clicked.connect(self._pick)
        row_layout.addWidget(self._browse)

        self._mount(row)

    def _pick(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择路径", self._edit.text() or str(Path.home()))
        if selected:
            self._edit.setText(selected)

    def get_value(self) -> Any:
        return self._edit.text()

    def set_value(self, value: Any) -> None:
        self._edit.setText("" if value is None else str(value))
