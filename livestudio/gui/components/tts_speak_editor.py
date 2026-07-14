"""当前模型 TTS 发声配置编辑器:供应商切换 + 共享参数

顶部 ``SegmentedWidget`` 按 kind 切换供应商(切换即存 kind);下方 ``QStackedWidget`` 一次只
显示激活供应商的 ``ConfigEditor``(音色等 BaseModel 槽)。供应商列表从
``TTSpeakControllerSettings`` 中 **BaseModel 字段** 内省,标量/共享字段(如字幕字速)
单独用一份 ConfigEditor,不再误当作供应商。

无配置(未连接/未加载模型)时内部控件隐藏、组件留空;整段是否可见由宿主(AudioView)控制。
"""

from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel, Field, create_model
from pydantic_core import PydanticUndefined
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget, SubtitleLabel

from livestudio.gui.components.config_editor import ConfigEditor
from livestudio.gui.constants import TTS_PROVIDER_LABEL
from livestudio.services.animations.controllers.config import TTSpeakControllerSettings


def _is_basemodel_type(annotation: object) -> bool:
    """字段注解是否为 BaseModel 子类(供应商 speak 配置槽)。"""

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    for arg in get_args(annotation):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return True
    return False


def _provider_field_names() -> list[str]:
    return [
        name
        for name, info in TTSpeakControllerSettings.model_fields.items()
        if name != "kind" and _is_basemodel_type(info.annotation)
    ]


def _shared_settings_model() -> type[BaseModel]:
    """从 TTSpeakControllerSettings 抽出非 kind、非供应商槽的共享字段模型。"""

    fields: dict[str, Any] = {}
    for name, info in TTSpeakControllerSettings.model_fields.items():
        if name == "kind" or _is_basemodel_type(info.annotation):
            continue
        annotation = info.annotation
        if annotation is None:
            continue
        if info.default is not PydanticUndefined:
            default = info.default
        elif info.default_factory is not None:
            default = Field(default_factory=info.default_factory, description=info.description or "")
            fields[name] = (annotation, default)
            continue
        else:
            default = ...
        fields[name] = (
            annotation,
            Field(default, description=info.description or ""),
        )
    if not fields:
        # 无共享字段时仍返回可实例化的空模型,避免编辑器分支特殊处理
        return create_model("_TTSpeakSharedSettings", __base__=BaseModel)
    return create_model("_TTSpeakSharedSettings", __base__=BaseModel, **fields)


_SharedSettings = _shared_settings_model()


class TtsSpeakEditor(QWidget):
    """当前模型 TTS 发声配置:供应商标签切换(即存 kind)+ 激活家音色 + 共享参数。"""

    saved = Signal(object)  # 发出 TTSpeakControllerSettings(kind 切换或配置变更后)
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

        # 共享参数(字幕字速等标量字段),与供应商槽并列
        if _SharedSettings.model_fields:
            box_layout.addWidget(SubtitleLabel("字幕与通用", self._box))
            self._shared_editor: ConfigEditor[Any] | None = ConfigEditor(
                _SharedSettings,
                scrollable=False,
                parent=self._box,
            )
            self._shared_editor.saved.connect(self._on_shared_saved)
            self._shared_editor.validationFailed.connect(self.validationFailed.emit)
            box_layout.addWidget(self._shared_editor)
        else:
            self._shared_editor = None

        outer.addWidget(self._box)

        self._build_providers()
        self._segment.currentItemChanged.connect(self._on_kind_changed)
        self._show_loaded(False)

    def _build_providers(self) -> None:
        """按 TTSpeakControllerSettings 中 BaseModel 字段建供应商标签与各家 ConfigEditor。"""

        for name in _provider_field_names():
            info = TTSpeakControllerSettings.model_fields[name]
            cfg_type = info.annotation
            if not isinstance(cfg_type, type) or not issubclass(cfg_type, BaseModel):
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
        if self._shared_editor is not None:
            shared_data = {
                name: getattr(settings, name) for name in _SharedSettings.model_fields
            }
            self._shared_editor.load(_SharedSettings.model_validate(shared_data))

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

    def _on_shared_saved(self, shared: Any) -> None:
        if self._settings is None:
            return
        if not isinstance(shared, BaseModel):
            return
        new_settings = self._settings.model_copy(update=shared.model_dump())
        self._settings = new_settings
        self.saved.emit(new_settings)
