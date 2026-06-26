"""通用配置编辑器顶层容器

把一个 Pydantic 模型渲染成可编辑表单,提供保存/重载,保存时用 model_validate 全量
校验并把错误按 loc 映射回字段。写回遵循「dump → 覆盖叶子 → model_validate」,不用 setattr。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, SingleDirectionScrollArea, StrongBodyLabel

from ._base import FieldEditor
from ._factory import create_editor
from ._schema import iter_field_specs
from ._schema_types import ChoicesProvider

ModelT = TypeVar("ModelT", bound=BaseModel)

# 保存成功回调:拿到校验后的新模型实例,由调用方决定如何持久化(模式 A/B)。
SaveHandler = Callable[[BaseModel], None]


class ConfigEditor(QWidget, Generic[ModelT]):
    """单个 Pydantic 模型的可编辑表单"""

    saved = Signal(object)  # 发出校验通过的新模型实例
    validationFailed = Signal(str)
    reloadRequested = Signal()  # 重载按钮:由宿主决定如何刷新(重读盘/重新枚举候选)

    def __init__(
        self,
        model_type: type[ModelT],
        *,
        choices_providers: Mapping[str, ChoicesProvider] | None = None,
        scrollable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model_type = model_type
        self._original: ModelT | None = None

        # 扁平表单:顶层字段直接纵向堆叠;容器型字段就地折叠展开(无内部 QStackedWidget/导航)。
        # scrollable=True 时字段区进垂直滚动区、动作条常驻滚动区外底部(平台页:内容长,按钮永远可见);
        # scrollable=False 时纯纵向堆叠,由宿主页面统一滚动(音频页:表单矮,避免滚动套滚动)。
        # scrollable 时编辑器需纵向扩展填满宿主,内部滚动区才有可用视口;非滚动时用 Minimum
        # 避免被宿主 stretch 压扁(卡片挤重叠)。
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if scrollable else QSizePolicy.Policy.Minimum,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 字段表单容器:顶层字段直接用 QVBoxLayout 纵向堆叠卡片。不用 SettingCardGroup:它内部的
        # ExpandLayout 按子部件当前 height() 绝对定位,套了一层布局的 FieldEditor 包装器
        # 高度算不准会导致卡片重叠;QVBoxLayout 正确尊重每张卡的 sizeHint,不会重叠。
        fields = QWidget(self)
        fields_layout = QVBoxLayout(fields)
        # 留出左右内边距:卡片不顶满页面边缘(scrollable 时右侧再留出滚动条空间)。
        fields_layout.setContentsMargins(4, 0, 12 if scrollable else 4, 0)
        fields_layout.setSpacing(8)
        self._group_title = StrongBodyLabel("配置", fields)
        fields_layout.addWidget(self._group_title)

        self._editors: dict[str, FieldEditor] = {}
        for spec in iter_field_specs(model_type, choices_providers=choices_providers):
            editor = create_editor(spec, fields)
            self._editors[spec.name] = editor
            fields_layout.addWidget(editor)
        fields_layout.addStretch(1)

        if scrollable:
            scroll = SingleDirectionScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.enableTransparentBackground()
            fields.setStyleSheet("background: transparent;")
            scroll.setWidget(fields)
            root.addWidget(scroll, 1)
        else:
            root.addWidget(fields)

        # 动作条:scrollable 时常驻滚动区之外(永远可见);否则跟随内容。左右留白与字段区对齐。
        buttons = QWidget(self)
        button_layout = QVBoxLayout(buttons)
        button_layout.setContentsMargins(4, 4, 4, 0)
        self._reload_button = PushButton("重载", buttons)
        self._reload_button.clicked.connect(self._on_reload)
        self._save_button = PrimaryPushButton("保存", buttons)
        self._save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self._reload_button)
        button_layout.addWidget(self._save_button)
        root.addWidget(buttons)

    def load(self, config: ModelT) -> None:
        """用模型实例填充表单。

        先刷新注入候选的下拉(如设备列表可能已变),再 set_value,确保已保存的值
        (如 device_index)能在最新候选里命中。
        """

        self._original = config
        self._refresh_injected_choices()
        # json 模式:frozenset→list、Enum→str、枚举键 dict→str 键 —— 子编辑器拿到的全是可编辑基元,
        # 也让只读子树的 YAML dump 不再遇到无法表示的 frozenset/Enum 实例。
        dumped = config.model_dump(mode="json")
        for name, editor in self._editors.items():
            if name in dumped:
                editor.set_value(dumped[name])
            editor.clear_errors()

    def _refresh_injected_choices(self) -> None:
        """重建带外部注入候选的下拉项(候选随运行时变化,如音频设备热插拔)"""

        from ._choice import ChoiceEditor

        for editor in self._editors.values():
            if isinstance(editor, ChoiceEditor) and editor.spec.choices_provider is not None:
                editor.refresh_choices()

    def collect(self) -> ModelT:
        """收集表单值并 model_validate,失败抛 ValidationError(保留 loc 供映射)"""

        # 与 load 一致用 json 模式作基准:叶子覆盖后由 model_validate 把 list 收回 frozenset、
        # str 收回 Enum、str 键收回枚举键 —— 编辑器全程只碰基元,领域模型类型由 pydantic 负责回灌。
        base: dict[str, Any] = self._original.model_dump(mode="json") if self._original is not None else {}
        for name, editor in self._editors.items():
            base[name] = editor.get_value()
        return self._model_type.model_validate(base)

    def request_save(self) -> None:
        """触发一次校验+保存(供宿主的外部按钮调用)"""

        self._on_save()

    def _on_save(self) -> None:
        for editor in self._editors.values():
            editor.clear_errors()
        try:
            validated = self.collect()
        except ValidationError as exc:
            self._show_errors(exc)
            return
        # 保存成功后把基线更新为已保存配置,使「重载」回到刚保存的状态而非启动时的旧快照
        self._original = validated
        self.saved.emit(validated)

    def _show_errors(self, exc: ValidationError) -> None:
        messages: list[str] = []
        for error in exc.errors():
            loc = error["loc"]
            message = error["msg"]
            messages.append(f"{'.'.join(str(part) for part in loc) or '<root>'}: {message}")
            if loc and isinstance(loc[0], str):
                editor = self._editors.get(loc[0])
                if editor is not None:
                    editor.dispatch_error(loc[1:], message)
        self.validationFailed.emit("; ".join(messages))

    def _on_reload(self) -> None:
        self.reloadRequested.emit()
        if self._original is not None:
            self.load(self._original)
