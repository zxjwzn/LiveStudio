"""exotic 子树兜底:就地展开为只读 YAML

frozenset / 判别联合 / 枚举键 dict 等 v1 不安全编辑的字段,以只读 YAML 呈现。
load 时持有原始值,get_value 原样回灌,确保写回时这些子树不被破坏。懒建:首次展开才建 TextEdit。
"""

from __future__ import annotations

from typing import Any

import yaml
from PySide6.QtWidgets import QWidget
from qfluentwidgets import TextEdit

from ._expandable import _ContainerEditor, indent_for_depth
from ._schema_types import FieldSpec


class ReadOnlyEditor(_ContainerEditor):
    """就地展开为只读 YAML;保存时原样返回加载时的值"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._raw: Any = None
        self._view: TextEdit | None = None
        self._card.setContent(f"{spec.description}(只读)" if spec.description else "只读")

    def _ensure_built(self) -> None:
        body = self._card.body_layout()
        body.setContentsMargins(indent_for_depth(1), 0, 0, 0)
        self._view = TextEdit(self._card)
        self._view.setReadOnly(True)
        body.addWidget(self._view)
        self._render()

    def _render(self) -> None:
        if self._view is None:
            return
        try:
            text = yaml.safe_dump(self._raw, allow_unicode=True, sort_keys=False)
        except yaml.YAMLError:
            text = str(self._raw)
        self._view.setPlainText(text)

    def get_value(self) -> Any:
        return self._raw

    def set_value(self, value: Any) -> None:
        self._raw = value
        self._render()
