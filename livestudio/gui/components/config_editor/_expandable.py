"""可就地展开的容器卡片 + 容器型字段编辑器基类

容器型字段(嵌套模型/list/dict/只读)用 _ExpandableCard 渲染:头部行(图标+标题+副标题+chevron)
与 leaf 的 SettingCard 视觉一致,头部下方是默认折叠的 body。首次展开才构建子内容(懒加载),
子内容缩进区分层级,全程同一页、无跳页。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, FluentStyleSheet, IconWidget, TransparentToolButton, qconfig
from qfluentwidgets import FluentIcon as FIF

from ._base import FieldEditor
from ._schema_types import FieldSpec, resolve_icon
from .constants import ERROR_COLOR, INDENT_MAX, INDENT_STEP


def _rotated_chevron_down() -> QIcon:
    """把细线 CHEVRON_RIGHT 顺时针旋转 90° 得到「下箭头」,与折叠态右箭头同款同粗。

    qfluentwidgets 无细线版 CHEVRON_DOWN(只有粗体 *_MED),ARROW_DOWN 也比 CHEVRON_RIGHT
    略粗;用同一图标旋转,保证展开/折叠两态箭头粗细完全一致。按当前主题渲染。
    """

    size = 64
    src = QPixmap(size, size)
    src.fill(Qt.GlobalColor.transparent)
    painter = QPainter(src)
    FIF.CHEVRON_RIGHT.icon().paint(painter, 0, 0, size, size)
    painter.end()
    rotated = src.transformed(QTransform().rotate(90), Qt.TransformationMode.SmoothTransformation)
    return QIcon(rotated)


class _ExpandableCard(CardWidget):
    """头部(图标+标题+副标题+chevron)+ 可折叠 body 的卡片,默认折叠"""

    expandedChanged = Signal(bool)

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._default_content = spec.description or ""
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        self._icon = IconWidget(resolve_icon(spec.icon), header)
        self._icon.setFixedSize(20, 20)
        header_layout.addWidget(self._icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        # 标题/副标题用裸 QLabel + SettingCard 同款 objectName,并 apply SETTING_CARD 样式,
        # 使字体/字号/字色与音频页等叶子 SettingCard 完全一致(协调),字色交全局 QSS 随主题。
        self._title = QLabel(spec.label, header)
        self._title.setObjectName("titleLabel")
        text_box.addWidget(self._title)
        self._content = QLabel(self._default_content, header)
        self._content.setObjectName("contentLabel")
        self._content.setWordWrap(True)
        text_box.addWidget(self._content)
        header_layout.addLayout(text_box, 1)

        self._toggle = TransparentToolButton(FIF.CHEVRON_RIGHT, header)
        self._toggle.clicked.connect(lambda: self.set_expanded(not self._expanded))
        header_layout.addWidget(self._toggle)
        # 旋转图标是固定色的 QPixmap,不随主题自动重绘;展开态下切主题时重设箭头跟随明暗
        qconfig.themeChanged.connect(self._refresh_toggle_icon)

        # 整个头部可点击切换(头部任意处点击=展开/收起)
        header.mousePressEvent = self._on_header_clicked
        outer.addWidget(header)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 4, 0, 0)
        self._body_layout.setSpacing(8)
        self._body.setVisible(False)
        outer.addWidget(self._body)

        FluentStyleSheet.SETTING_CARD.apply(self)

    def _on_header_clicked(self, event: object) -> None:
        _ = event
        self.set_expanded(not self._expanded)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._body.setVisible(expanded)
        # 展开=旋转 90° 的细 CHEVRON_RIGHT(下箭头),折叠=细 CHEVRON_RIGHT(右箭头),两态同款同粗
        self._toggle.setIcon(_rotated_chevron_down() if expanded else FIF.CHEVRON_RIGHT)
        self.expandedChanged.emit(expanded)

    def _refresh_toggle_icon(self) -> None:
        """主题切换后,展开态的旋转箭头(固定色 QPixmap)需按新主题重绘"""

        if self._expanded:
            self._toggle.setIcon(_rotated_chevron_down())

    def is_expanded(self) -> bool:
        return self._expanded

    def setTitle(self, text: str) -> None:
        self._title.setText(text)

    def setContent(self, text: str) -> None:
        self._default_content = text
        self._content.setStyleSheet("")
        self._content.setText(text)

    def set_error_text(self, message: str | None) -> None:
        if message:
            self._content.setText("存在校验错误,展开查看")
            self._content.setStyleSheet(f"#contentLabel {{ color: {ERROR_COLOR}; }}")
        else:
            # 清空内联样式即回到 SETTING_CARD 全局 QSS 控制的副标题色(随主题)
            self._content.setStyleSheet("")
            self._content.setText(self._default_content)


def indent_for_depth(depth: int) -> int:
    """按层级算缩进(封顶,防溢出)"""

    return min(depth * INDENT_STEP, INDENT_MAX)


class _ContainerEditor(FieldEditor):
    """容器型字段基类:就地折叠展开 + 首次展开懒建。

    子类实现 `_ensure_built()`(把子内容建进 self._card.body_layout())。
    懒加载:折叠时只持有数据;首次展开触发构建。
    """

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(spec, parent)
        self._built = False
        self._pending_errors: list[tuple[tuple[Any, ...], str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._card = _ExpandableCard(spec, self)
        self._card.expandedChanged.connect(self._on_expanded)
        outer.addWidget(self._card)

    def _on_expanded(self, expanded: bool) -> None:
        if expanded and not self._built:
            self._build()

    def _build(self) -> None:
        if self._built:
            return
        self._ensure_built()
        self._built = True
        pending = self._pending_errors
        self._pending_errors = []
        for loc, message in pending:
            self.dispatch_error(loc, message)

    def _ensure_built(self) -> None:
        """子类实现:把子内容建进 self._card.body_layout()"""

        raise NotImplementedError

    def expand_to_build(self) -> None:
        """展开并确保已构建(供错误自动展开调用)"""

        self._card.set_expanded(True)
        self._build()

    def set_error(self, message: str | None) -> None:
        self._card.set_error_text(message)

    def dispatch_error(self, loc: tuple[Any, ...], message: str) -> None:
        # 深层错误:未建则暂存 + 自动展开构建,再递归派发到子编辑器
        if loc and not self._built:
            self._pending_errors.append((loc, message))
            self.set_error(message)
            self.expand_to_build()
            return
        super().dispatch_error(loc, message)

    def clear_errors(self) -> None:
        self._pending_errors.clear()
        super().clear_errors()

    def child_editors(self) -> Iterable[FieldEditor]:
        return ()
