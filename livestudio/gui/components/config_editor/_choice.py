"""选择字段编辑器:Literal / Enum / 外部注入候选 → ComboBox(SettingCard 横条)"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget
from qfluentwidgets import ComboBox

from ._atomic import _CardEditor
from ._schema_types import FieldSpec


class ChoiceEditor(_CardEditor):
    """下拉选择;候选来自 spec.choices 或 spec.choices_provider(显示名/写回值分离)"""

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._combo = ComboBox(self)
        self._combo.setMinimumWidth(180)

        # 每项写回值与显示名分离:value 存进 itemData,文本仅作展示
        self._values: list[Any] = []
        self._populate()
        self._combo.currentIndexChanged.connect(lambda _: self.valueChanged.emit())
        self._mount(self._combo)

    def _populate(self) -> None:
        self._combo.clear()
        self._values.clear()
        if self.spec.choices_provider is not None:
            for display, value in self.spec.choices_provider():
                self._combo.addItem(display)
                self._values.append(value)
        else:
            for value in self.spec.choices:
                self._combo.addItem(str(value))
                self._values.append(value)

    def refresh_choices(self) -> None:
        """重新拉取注入候选(如音频设备热插拔后)"""

        current = self.get_value()
        self._populate()
        self.set_value(current)

    def get_value(self) -> Any:
        index = self._combo.currentIndex()
        if 0 <= index < len(self._values):
            return self._values[index]
        return None

    def set_value(self, value: Any) -> None:
        for index, candidate in enumerate(self._values):
            if candidate == value:
                self._combo.setCurrentIndex(index)
                return
