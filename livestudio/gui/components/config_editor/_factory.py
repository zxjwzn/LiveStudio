"""编辑器工厂:FieldSpec → FieldEditor,递归入口

为打破与 _complex/_union 的循环依赖,具体编辑器在函数内惰性导入。
"""

from __future__ import annotations

from typing import Any

from pydantic.fields import FieldInfo
from PySide6.QtWidgets import QWidget

from ._base import FieldEditor
from ._schema import build_field_spec
from ._schema_types import FieldKind, FieldSpec


def create_editor(spec: FieldSpec, parent: QWidget | None = None) -> FieldEditor:
    """按 FieldSpec.kind 分派到具体编辑器"""

    from ._atomic import BoolEditor, ColorEditor, FloatEditor, IntEditor, PathEditor, StrEditor
    from ._choice import ChoiceEditor
    from ._complex import DictEditor, ListEditor, ModelEditor
    from ._readonly import ReadOnlyEditor
    from ._tagged_union import TaggedUnionEditor
    from ._union import OptionalEditor, UnionEditor

    dispatch: dict[FieldKind, type[FieldEditor]] = {
        FieldKind.BOOL: BoolEditor,
        FieldKind.INT: IntEditor,
        FieldKind.FLOAT: FloatEditor,
        FieldKind.STR: StrEditor,
        FieldKind.PATH: PathEditor,
        FieldKind.COLOR: ColorEditor,
        FieldKind.CHOICE: ChoiceEditor,
        FieldKind.MODEL: ModelEditor,
        FieldKind.LIST: ListEditor,
        FieldKind.DICT: DictEditor,
        FieldKind.OPTIONAL: OptionalEditor,
        FieldKind.UNION: UnionEditor,
        FieldKind.TAGGED_UNION: TaggedUnionEditor,
        FieldKind.READONLY: ReadOnlyEditor,
    }
    editor_type = dispatch[spec.kind]
    return editor_type(spec, parent)


def create_editor_for_annotation(
    annotation: Any, name: str, parent: QWidget | None = None, *, bare: bool = False
) -> FieldEditor:
    """为没有 FieldInfo 的内联类型(list 元素 / dict 值 / union 成员)构造编辑器。

    用一个仅含 annotation 的 FieldInfo 复用同一套解析逻辑,保证递归一致。
    bare=True 时清空 label/description 并置 spec.bare,供容器型编辑器复用控件而不画卡片。
    """

    info = FieldInfo(annotation=annotation)
    spec = build_field_spec(name, info)
    if bare:
        spec.label = ""
        spec.description = ""
        spec.bare = True
    return create_editor(spec, parent)
