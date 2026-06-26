"""字段编辑器基类

每个编辑器是一个自包含 QWidget,负责渲染单个字段(标签 + 控件 + 描述 + 行内错误),
并暴露统一的取值/赋值/校验错误接口。容器型编辑器(模型/列表/字典)通过 child_by_key
把根级 ValidationError 的 loc 路径逐层派发到出错的子编辑器。
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ._schema_types import FieldSpec


class FieldEditor(QWidget):
    """单字段编辑器抽象基类"""

    valueChanged = Signal()

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec

    @abstractmethod
    def get_value(self) -> Any:
        """返回当前控件值(标量 / list / dict / 嵌套 dict),供写回 model_validate"""

    @abstractmethod
    def set_value(self, value: Any) -> None:
        """用给定值填充控件"""

    def set_error(self, message: str | None) -> None:
        """显示或清除本字段的行内错误(默认无错误展示,子类可覆盖)"""

        _ = message

    def child_by_key(self, key: Any) -> FieldEditor | None:
        """按 loc 路径段返回子编辑器;非容器返回 None"""

        _ = key
        return None

    def child_editors(self) -> Iterable[FieldEditor]:
        """返回直接子编辑器,用于递归清除错误;非容器返回空"""

        return ()

    def clear_errors(self) -> None:
        """递归清除自身与所有子编辑器的错误展示"""

        self.set_error(None)
        for child in self.child_editors():
            child.clear_errors()

    def dispatch_error(self, loc: tuple[Any, ...], message: str) -> None:
        """把一条校验错误按 loc 派发到对应(子)编辑器"""

        if not loc:
            self.set_error(message)
            return
        child = self.child_by_key(loc[0])
        if child is None:
            # 找不到对应子编辑器(如字典键/未展开项),退化为在本级展示
            self.set_error(message)
            return
        child.dispatch_error(loc[1:], message)
