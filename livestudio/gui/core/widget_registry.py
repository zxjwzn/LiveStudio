"""可插拔配置控件渲染注册表。

通用配置编辑器的核心：把「数据类型」与「渲染控件」解耦。

- ConfigFieldVM 带 value_type（数据是什么）+ widget（用哪个控件 key）。
- 每个 widget key 对应一个 renderer：拿到字段描述符与一个 emit 回调，
  返回一个 flet 控件。renderer 负责把用户输入经 emit(value) 上报。
- "auto" 不是注册项，而是按 value_type 解析到默认 widget（见 DEFAULT_WIDGETS）。

这样：同一个 int 可在 number / slider / spinbox 间切换，只改 widget 字段；
新增自定义控件（旋钮、颜色选择器）= register 一个 renderer，编辑器零改动。

renderer 签名：(field, emit) -> ft.Control
- field: ConfigFieldVM 描述符
- emit:  Callable[[Any], None]，renderer 在用户改动时调用上报新值
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import flet as ft

from .view_models import ConfigFieldVM

if TYPE_CHECKING:
    from .choices_registry import ChoicesRegistry

# renderer 上报值的回调
EmitValue = Callable[[Any], None]
# 调度一个协程工厂到事件循环（通常包 page.run_task）
Scheduler = Callable[[Callable[[], Awaitable[None]]], None]


@dataclass
class RenderContext:
    """renderer 渲染单个字段时拿到的全部依赖。

    把 emit 与可选服务（异步调度、动态选项注册表、刷新回调）一起交给 renderer，
    使每个控件都能完全自管理——包括动态下拉这类需要异步拉取的复杂控件，
    无需编辑器为某种控件开特例。
    """

    field: ConfigFieldVM
    emit: EmitValue  # renderer 在用户改动时调用上报新值
    scheduler: Scheduler | None = None  # 异步控件用：调度协程到事件循环
    choices_registry: "ChoicesRegistry | None" = None  # 动态下拉用
    safe_update: Callable[[], None] = lambda: None  # 异步回填后刷新 UI


# 控件渲染器：拿渲染上下文，产出 flet 控件
WidgetRenderer = Callable[[RenderContext], ft.Control]

# value_type -> 默认 widget key（widget="auto" 时用）
DEFAULT_WIDGETS: dict[str, str] = {
    "bool": "switch",
    "int": "number",
    "float": "number",
    "str": "text",
    "enum": "dropdown",
}


class WidgetRegistry:
    """按 key 注册/解析配置控件渲染器。"""

    def __init__(self) -> None:
        self._renderers: dict[str, WidgetRenderer] = {}

    def register(self, widget: str, renderer: WidgetRenderer) -> None:
        """注册一个控件渲染器；同 key 重复注册将覆盖。"""

        self._renderers[widget] = renderer

    def has(self, widget: str) -> bool:
        """是否存在该控件渲染器。"""

        return widget in self._renderers

    def resolve_widget_key(self, field: ConfigFieldVM) -> str:
        """把 field.widget（可能是 "auto"）解析为具体的 widget key。"""

        if field.widget and field.widget != "auto":
            return field.widget
        return DEFAULT_WIDGETS.get(field.value_type, "")

    def render(self, ctx: RenderContext) -> ft.Control | None:
        """渲染字段控件；无匹配 renderer 时返回 None（由编辑器兜底）。"""

        renderer = self._renderers.get(self.resolve_widget_key(ctx.field))
        if renderer is None:
            return None
        return renderer(ctx)
