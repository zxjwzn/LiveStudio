"""判别联合编辑器:带 discriminator 的多 BaseModel 联合(如 ExpressionRule)

就地折叠卡(_ContainerEditor)内:顶部 ComboBox 选判别值(kind),下方就地渲染所选成员的字段表单。
切换 kind 重建子表单;get_value 产出 {判别字段: 选中值, **成员字段值},由 pydantic 按 kind 判别回灌。
判别字段本身由 ComboBox 掌控,不重复渲染。懒建:首次展开才构建。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import ComboBox

from ._base import FieldEditor
from ._expandable import _ContainerEditor, indent_for_depth
from ._factory import create_editor
from ._schema import iter_field_specs
from ._schema_types import FieldSpec


class TaggedUnionEditor(_ContainerEditor):
    """判别联合:ComboBox 选 kind + 所选成员的就地字段表单"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._discriminator = spec.discriminator or "kind"
        self._members: dict[str, type] = dict(spec.union_members)
        self._kinds: list[str] = [value for value, _ in spec.union_members]
        self._value: dict[str, Any] = {}
        self._current_kind: str | None = None
        self._selector: ComboBox | None = None
        self._member_container: QWidget | None = None
        self._member_layout: QVBoxLayout | None = None
        self._children: dict[str, FieldEditor] = {}
        self._update_summary()

    def _ensure_built(self) -> None:
        body = self._card.body_layout()
        body.setContentsMargins(indent_for_depth(1), 0, 0, 0)

        self._selector = ComboBox(self._card)
        self._selector.setMinimumWidth(180)
        for kind in self._kinds:
            self._selector.addItem(kind)
        self._selector.setEnabled(not self.spec.readonly)
        body.addWidget(self._selector)

        self._member_container = QWidget(self._card)
        self._member_layout = QVBoxLayout(self._member_container)
        self._member_layout.setContentsMargins(0, 0, 0, 0)
        self._member_layout.setSpacing(8)
        body.addWidget(self._member_container)

        kind = self._value.get(self._discriminator)
        index = self._kinds.index(kind) if kind in self._kinds else 0
        blocker = QSignalBlocker(self._selector)
        self._selector.setCurrentIndex(index)
        del blocker
        self._rebuild_member(self._kinds[index])
        self._selector.currentIndexChanged.connect(self._on_kind_changed)

    def _on_kind_changed(self, index: int) -> None:
        if 0 <= index < len(self._kinds):
            self._rebuild_member(self._kinds[index])
            self.valueChanged.emit()

    def _rebuild_member(self, kind: str) -> None:
        if self._member_container is None or self._member_layout is None:
            return
        for editor in self._children.values():
            editor.setParent(None)
            editor.deleteLater()
        self._children.clear()

        member = self._members[kind]
        for child_spec in iter_field_specs(member):
            if child_spec.name == self._discriminator:
                continue  # 判别字段由 ComboBox 掌控,不重复渲染
            editor = create_editor(child_spec, self._member_container)
            editor.valueChanged.connect(self.valueChanged.emit)
            self._children[child_spec.name] = editor
            self._member_layout.addWidget(editor)
            if child_spec.name in self._value:
                blocker = QSignalBlocker(editor)
                editor.set_value(self._value[child_spec.name])
                del blocker
        self._current_kind = kind
        self._update_summary()

    def _update_summary(self) -> None:
        kind = self._current_kind or self._value.get(self._discriminator, "")
        base = self.spec.description or ""
        self._card.setContent(f"{base}({kind})".lstrip() if kind else base)

    def get_value(self) -> Any:
        if not self._built:
            return dict(self._value)
        kind = self._current_kind or (self._kinds[0] if self._kinds else "")
        result: dict[str, Any] = {self._discriminator: kind}
        for name, editor in self._children.items():
            result[name] = editor.get_value()
        return result

    def set_value(self, value: Any) -> None:
        self._value = dict(value) if isinstance(value, dict) else {}
        self._update_summary()
        if not self._built or self._selector is None:
            return
        kind = self._value.get(self._discriminator)
        index = self._kinds.index(kind) if kind in self._kinds else 0
        blocker = QSignalBlocker(self._selector)
        self._selector.setCurrentIndex(index)
        del blocker
        self._rebuild_member(self._kinds[index])

    def child_by_key(self, key: Any) -> FieldEditor | None:
        return self._children.get(key)

    def child_editors(self) -> Iterable[FieldEditor]:
        return self._children.values()
