"""当前模型 TTS 发声配置编辑器:供应商切换 + 仅展示激活家

顶部 ``SegmentedWidget`` 按 kind 切换供应商(切换即存 kind);下方 ``QStackedWidget`` 一次只
显示激活供应商的 ``ConfigEditor``(其自带保存按钮写音色参数)。供应商列表与各家编辑器类型
从 ``TTSpeakControllerSettings.model_fields`` 内省,新增供应商零代码自动出现新标签与编辑器。

无配置(未连接/未加载模型)时内部控件隐藏、组件留空;整段是否可见由宿主(AudioView)控制。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget

from livestudio.gui.components.config_editor import ConfigEditor
from livestudio.gui.constants import TTS_PROVIDER_LABEL
from livestudio.services.animations.controllers.config import TTSpeakControllerSettings


class TtsSpeakEditor(QWidget):
    """当前模型 TTS 发声配置:供应商标签切换(即存 kind)+ 激活家音色参数编辑。"""

    saved = Signal(object)  # 发出 TTSpeakControllerSettings(kind 切换或某供应商配置变更后)
    validationFailed = Signal(str)  # 转发子编辑器校验失败

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings: TTSpeakControllerSettings | None = None
        self._suppress_segment = False
        self._editors: dict[str, ConfigEditor[Any]] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._box = QWidget(self)
        box_layout = QVBoxLayout(self._box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(8)

        # 供应商切换条:横向占自然宽度 + stretch 占位,长度接近音频页麦克风/TTS 切换条(不顶满)
        self._segment = SegmentedWidget(self._box)
        segment_row = QHBoxLayout()
        segment_row.setContentsMargins(0, 0, 0, 0)
        segment_row.addWidget(self._segment)
        segment_row.addStretch(1)
        box_layout.addLayout(segment_row)

        self._stack = QStackedWidget(self._box)
        box_layout.addWidget(self._stack)
        outer.addWidget(self._box)

        self._build_providers()
        self._segment.currentItemChanged.connect(self._on_kind_changed)
        self._show_loaded(False)

    def _build_providers(self) -> None:
        """按 TTSpeakControllerSettings 并列字段建供应商标签与各家 ConfigEditor。"""

        for name, info in TTSpeakControllerSettings.model_fields.items():
            if name == "kind":
                continue
            cfg_type = info.annotation
            if cfg_type is None:
                continue
            self._segment.addItem(routeKey=name, text=TTS_PROVIDER_LABEL.get(name, name))
            editor: ConfigEditor[Any] = ConfigEditor(cfg_type, scrollable=False, parent=self._stack)
            editor.saved.connect(lambda cfg, k=name: self._on_sub_saved(k, cfg))
            editor.validationFailed.connect(self.validationFailed.emit)
            self._editors[name] = editor
            self._stack.addWidget(editor)

    def load(self, settings: TTSpeakControllerSettings | None) -> None:
        """加载当前模型发声配置;None 时隐藏内部控件(留空,由宿主隐藏整段)。"""

        self._settings = settings
        if settings is None:
            self._show_loaded(False)
            return
        self._show_loaded(True)
        # 程序化置切换条不应触发自动保存(避免初始化/刷新时多余写盘)
        self._suppress_segment = True
        self._segment.setCurrentItem(settings.kind)
        self._suppress_segment = False
        active = self._editors.get(settings.kind)
        if active is not None:
            self._stack.setCurrentWidget(active)
        for name, editor in self._editors.items():
            editor.load(getattr(settings, name))

    def _show_loaded(self, loaded: bool) -> None:
        self._box.setVisible(loaded)

    def _on_kind_changed(self, route_key: str) -> None:
        if self._suppress_segment or self._settings is None:
            return
        editor = self._editors.get(route_key)
        if editor is not None:
            self._stack.setCurrentWidget(editor)
        # 切换即存 kind(各供应商配置不变)
        new_settings = self._settings.model_copy(update={"kind": route_key})
        self._settings = new_settings
        self.saved.emit(new_settings)

    def _on_sub_saved(self, provider: str, sub_config: Any) -> None:
        if self._settings is None:
            return
        new_settings = self._settings.model_copy(update={provider: sub_config})
        self._settings = new_settings
        self.saved.emit(new_settings)
