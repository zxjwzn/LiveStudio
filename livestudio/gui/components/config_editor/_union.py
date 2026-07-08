"""联合字段编辑器:T | None(清除按钮) 与 多成员 Union(类型选择 + 动态子编辑器)

均渲染为 SettingCard 横条,组合控件挂在卡片右侧;内层成员用 bare 模式(只控件不画卡)。
"""

from __future__ import annotations

import typing
from collections.abc import Iterable
from typing import Any, Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget
from qfluentwidgets import ComboBox, PushButton

from ._atomic import _CardEditor
from ._base import FieldEditor
from ._factory import create_editor_for_annotation
from ._schema_types import FieldSpec
from .constants import PRIMITIVE_LABEL


def _member_label(annotation: Any) -> str:
    """把联合成员类型渲染成人类可读的选项名。"""

    if typing.get_origin(annotation) is Literal:
        values = ", ".join(str(value) for value in typing.get_args(annotation))
        return f"预设({values})"
    if annotation in PRIMITIVE_LABEL:
        return PRIMITIVE_LABEL[annotation]
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


class OptionalEditor(_CardEditor):
    """T | None:卡片右侧显示内层控件 + 「清除」按钮。

    清除=回到默认(写 None);用户一旦编辑内层控件即视为自定义值。
    """

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        inner_annotation = spec.inner_annotations[0] if spec.inner_annotations else str

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._inner = create_editor_for_annotation(inner_annotation, spec.label, row, bare=True)
        # 「是否为默认(None)」标记:清除后为 True;用户改动内层控件即转 False
        self._is_null = True
        self._inner.valueChanged.connect(self._on_inner_changed)
        row_layout.addWidget(self._inner, 1)

        self._clear = PushButton("清除", row)
        self._clear.setEnabled(not spec.readonly)
        self._clear.clicked.connect(self._on_clear)
        row_layout.addWidget(self._clear, 0, Qt.AlignmentFlag.AlignVCenter)
        self._mount(row)

    def _on_inner_changed(self) -> None:
        # 用户编辑内层控件 → 不再是默认值
        self._is_null = False
        self.valueChanged.emit()

    def _on_clear(self) -> None:
        self._is_null = True
        self.valueChanged.emit()

    def get_value(self) -> Any:
        if self._is_null:
            return None
        return self._inner.get_value()

    def set_value(self, value: Any) -> None:
        if value is None:
            self._is_null = True
            return
        self._is_null = False
        self._inner.set_value(value)

    def child_editors(self) -> Iterable[FieldEditor]:
        return (self._inner,)


class UnionEditor(_CardEditor):
    """多成员 Union:卡片右侧 类型下拉 + 按选中类型切换子编辑器;含 None 时附「无」选项"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._optional = spec.optional
        members = list(spec.inner_annotations)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._selector = ComboBox(row)
        self._selector.setMinimumWidth(120)
        row_layout.addWidget(self._selector)

        self._stack = QStackedWidget(row)
        row_layout.addWidget(self._stack, 1)

        self._editors: list[FieldEditor | None] = []
        for annotation in members:
            self._selector.addItem(_member_label(annotation))
            editor = create_editor_for_annotation(annotation, spec.label, self, bare=True)
            editor.valueChanged.connect(self.valueChanged.emit)
            self._editors.append(editor)
            self._stack.addWidget(editor)
        if self._optional:
            self._selector.addItem("无")
            placeholder = QWidget(self)
            self._editors.append(None)
            self._stack.addWidget(placeholder)

        self._selector.currentIndexChanged.connect(self._on_select)
        self._mount(row)

    def _on_select(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.valueChanged.emit()

    def get_value(self) -> Any:
        index = self._selector.currentIndex()
        if 0 <= index < len(self._editors):
            editor = self._editors[index]
            return None if editor is None else editor.get_value()
        return None

    def set_value(self, value: Any) -> None:
        if value is None and self._optional:
            self._selector.setCurrentIndex(len(self._editors) - 1)
            return
        # 选第一个能接受该值的成员编辑器(按声明顺序),失败则保持当前
        for index, editor in enumerate(self._editors):
            if editor is None:
                continue
            try:
                editor.set_value(value)
            except (TypeError, ValueError):
                continue
            self._selector.setCurrentIndex(index)
            return

    def child_editors(self) -> Iterable[FieldEditor]:
        return tuple(editor for editor in self._editors if editor is not None)
