"""复合字段编辑器:嵌套 BaseModel / list / dict

容器型编辑器**就地折叠展开 + 懒加载**:渲染为 _ExpandableCard(头部行 + 折叠 body),
只在用户首次展开时才构建子编辑器进 body(缩进区分层级),全程同一页、无跳页。未展开时仅
持有纯数据(dict/list),避免一次性急建几千个 widget。取值/赋值/错误派发在「未建」「已建」两态均成立。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import LineEdit, PushButton

from ._base import FieldEditor
from ._expandable import _ContainerEditor, indent_for_depth
from ._factory import create_editor, create_editor_for_annotation
from ._schema import iter_field_specs
from ._schema_types import FieldSpec


class ModelEditor(_ContainerEditor):
    """嵌套 BaseModel:就地展开为子字段表单;值为 {字段名: 子值} 的 dict"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        if spec.model_type is None:
            raise ValueError(f"ModelEditor 需要 model_type: {spec.name}")
        self._model_type = spec.model_type
        self._value: dict[str, Any] = {}
        self._children: dict[str, FieldEditor] = {}

    def _ensure_built(self) -> None:
        body = self._card.body_layout()
        body.setContentsMargins(indent_for_depth(1), 0, 0, 0)
        for child_spec in iter_field_specs(self._model_type):
            editor = create_editor(child_spec, self._card)
            editor.valueChanged.connect(self.valueChanged.emit)
            self._children[child_spec.name] = editor
            body.addWidget(editor)
        # 推入持有值(抑制 valueChanged,避免展开即显示为"已修改")
        for name, editor in self._children.items():
            if name in self._value:
                blocker = QSignalBlocker(editor)
                editor.set_value(self._value[name])
                del blocker

    def get_value(self) -> Any:
        # 未建:持有值即权威;已建:子 widget 值覆盖持有值(保留 hidden/未建模的 dump 键)
        merged = dict(self._value)
        for name, editor in self._children.items():
            merged[name] = editor.get_value()
        return merged

    def set_value(self, value: Any) -> None:
        self._value = dict(value) if isinstance(value, dict) else {}
        for name, editor in self._children.items():
            if name in self._value:
                blocker = QSignalBlocker(editor)
                editor.set_value(self._value[name])
                del blocker

    def child_by_key(self, key: Any) -> FieldEditor | None:
        return self._children.get(key)

    def child_editors(self) -> Iterable[FieldEditor]:
        return self._children.values()


class ListEditor(_ContainerEditor):
    """list[T]:就地展开为增删元素列表;值为 list"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._element_annotation = spec.inner_annotations[0] if spec.inner_annotations else str
        self._value: list[Any] = []
        self._items: list[FieldEditor] = []
        self._items_container: QWidget | None = None
        self._items_layout: QVBoxLayout | None = None
        self._populating = False
        self._update_summary()

    def _ensure_built(self) -> None:
        body = self._card.body_layout()
        body.setContentsMargins(indent_for_depth(1), 0, 0, 0)

        self._items_container = QWidget(self._card)
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(4)
        body.addWidget(self._items_container)

        add_button = PushButton("+ 新增", self._card)
        add_button.setEnabled(not self.spec.readonly)
        add_button.clicked.connect(self._add_blank)
        body.addWidget(add_button)

        # 填充持有值(抑制 valueChanged,避免展开即"脏")
        self._populating = True
        for element in self._value:
            self._add_item(element)
        self._populating = False
        self._update_summary()

    def _update_summary(self) -> None:
        count = len(self._items) if self._built else len(self._value)
        self._card.setContent(f"{self.spec.description or ''}(共 {count} 项)".lstrip())

    def _add_item(self, value: Any) -> None:
        if self._items_container is None or self._items_layout is None:
            return
        row = QWidget(self._items_container)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        editor = create_editor_for_annotation(self._element_annotation, f"[{len(self._items)}]", row)
        editor.valueChanged.connect(self.valueChanged.emit)
        if value is not None:
            blocker = QSignalBlocker(editor)
            editor.set_value(value)
            del blocker
        row_layout.addWidget(editor, 1)

        remove = PushButton("删除", row)
        remove.clicked.connect(lambda: self._remove(row, editor))
        row_layout.addWidget(remove)

        self._items.append(editor)
        self._items_layout.addWidget(row)
        self._update_summary()
        if not self._populating:
            self.valueChanged.emit()

    def _add_blank(self) -> None:
        self._add_item(None)

    def _remove(self, row: QWidget, editor: FieldEditor) -> None:
        self._items.remove(editor)
        row.setParent(None)
        row.deleteLater()
        self._update_summary()
        self.valueChanged.emit()

    def get_value(self) -> Any:
        if not self._built:
            return list(self._value)
        return [editor.get_value() for editor in self._items]

    def set_value(self, value: Any) -> None:
        self._value = list(value or [])
        if not self._built:
            self._update_summary()
            return
        for editor in list(self._items):
            editor.setParent(None)
            editor.deleteLater()
        self._items.clear()
        self._populating = True
        for element in self._value:
            self._add_item(element)
        self._populating = False
        self._update_summary()

    def child_by_key(self, key: Any) -> FieldEditor | None:
        if isinstance(key, int) and 0 <= key < len(self._items):
            return self._items[key]
        return None

    def child_editors(self) -> Iterable[FieldEditor]:
        return tuple(self._items)


class DictEditor(_ContainerEditor):
    """dict[K, V]:就地展开为增删键值对;值为 dict"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._value_annotation = spec.inner_annotations[1] if len(spec.inner_annotations) > 1 else str
        self._value: dict[str, Any] = {}
        self._rows: list[tuple[LineEdit, FieldEditor]] = []
        self._rows_container: QWidget | None = None
        self._rows_layout: QVBoxLayout | None = None
        self._populating = False
        self._update_summary()

    def _ensure_built(self) -> None:
        body = self._card.body_layout()
        body.setContentsMargins(indent_for_depth(1), 0, 0, 0)

        self._rows_container = QWidget(self._card)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        body.addWidget(self._rows_container)

        add_button = PushButton("+ 新增键值对", self._card)
        add_button.setEnabled(not self.spec.readonly)
        add_button.clicked.connect(lambda: self._add_row("", None))
        body.addWidget(add_button)

        self._populating = True
        for key, element in self._value.items():
            self._add_row(str(key), element)
        self._populating = False
        self._update_summary()

    def _update_summary(self) -> None:
        count = len(self._rows) if self._built else len(self._value)
        self._card.setContent(f"{self.spec.description or ''}(共 {count} 项)".lstrip())

    def _add_row(self, key: str, value: Any) -> None:
        if self._rows_container is None or self._rows_layout is None:
            return
        row = QWidget(self._rows_container)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        key_edit = LineEdit(row)
        key_edit.setPlaceholderText("键")
        key_edit.setText(key)
        key_edit.textChanged.connect(lambda _: self.valueChanged.emit())
        row_layout.addWidget(key_edit, 1)

        value_editor = create_editor_for_annotation(self._value_annotation, "值", row)
        value_editor.valueChanged.connect(self.valueChanged.emit)
        if value is not None:
            blocker = QSignalBlocker(value_editor)
            value_editor.set_value(value)
            del blocker
        row_layout.addWidget(value_editor, 2)

        remove = PushButton("删除", row)
        remove.clicked.connect(lambda: self._remove(row, key_edit, value_editor))
        row_layout.addWidget(remove)

        self._rows.append((key_edit, value_editor))
        self._rows_layout.addWidget(row)
        self._update_summary()
        if not self._populating:
            self.valueChanged.emit()

    def _remove(self, row: QWidget, key_edit: LineEdit, value_editor: FieldEditor) -> None:
        self._rows.remove((key_edit, value_editor))
        row.setParent(None)
        row.deleteLater()
        self._update_summary()
        self.valueChanged.emit()

    def get_value(self) -> Any:
        if not self._built:
            return dict(self._value)
        return {key_edit.text(): value_editor.get_value() for key_edit, value_editor in self._rows if key_edit.text()}

    def set_value(self, value: Any) -> None:
        self._value = dict(value) if isinstance(value, dict) else {}
        if not self._built:
            self._update_summary()
            return
        for _, value_editor in list(self._rows):
            value_editor.setParent(None)
            value_editor.deleteLater()
        self._rows.clear()
        self._populating = True
        for key, element in self._value.items():
            self._add_row(str(key), element)
        self._populating = False
        self._update_summary()
