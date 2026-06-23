"""数据驱动的通用配置编辑器。

按 ConfigSectionVM / ConfigFieldVM 递归渲染编辑控件，改动经 on_change(path, value)
增量回调。音频配置先用，P4 模型配置编辑器直接复用。

设计要点（三层解耦）：
- 数据类型（value_type）与控件（widget）分离：控件查 WidgetRegistry，同一个 int
  可在 number / slider / spinbox 间切换，只改 widget 字段。
- 动态下拉数据源：字段只带 choices_source key，背后静态/枚举/动态 API 都行，
  编辑器不关心；复杂逻辑收敛在 ChoicesRegistry 的 provider 里。
- 复合结构递归：group 固定子字段递归渲染（list/dict 变长结构留待后续）。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import flet as ft

from ..core.choices_registry import ChoicesRegistry
from ..core.mount_aware import MountAware
from ..core.theme import PALETTE, TYPE
from ..core.view_models import ConfigFieldVM
from ..core.widget_registry import RenderContext, WidgetRegistry
from .config_widgets import register_builtin_widgets

# 调度协程工厂到事件循环（视图注入，通常包 page.run_task）
Scheduler = Callable[[Callable[[], Awaitable[None]]], None]
# 配置项改动回调：(点路径, 新值)
OnChange = Callable[[str, Any], None]


def default_widget_registry() -> WidgetRegistry:
    """构造一个已注册内置控件的 WidgetRegistry。"""

    registry = WidgetRegistry()
    register_builtin_widgets(registry)
    return registry


class ConfigEditor(MountAware, ft.Column):
    """把 ConfigFieldVM 列表递归渲染成可编辑表单。"""

    def __init__(
        self,
        fields: list[ConfigFieldVM],
        on_change: OnChange,
        *,
        widget_registry: WidgetRegistry | None = None,
        choices_registry: ChoicesRegistry | None = None,
        scheduler: Scheduler | None = None,
    ) -> None:
        super().__init__(spacing=14, tight=True)
        self._fields = fields
        self._on_change = on_change
        self._widgets = widget_registry or default_widget_registry()
        self._choices = choices_registry
        self._scheduler = scheduler
        self.controls = _with_dividers([self._build_field(field) for field in fields])

    # —— 字段渲染（递归）——
    def _build_field(self, field: ConfigFieldVM) -> ft.Control:
        if field.value_type == "group":
            return self._build_group(field)

        control = self._render_control(field)
        label = ft.Text(field.label, size=TYPE.body, weight=ft.FontWeight.W_500, color=PALETTE.text)
        row = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[label, control],
        )
        if field.help:
            return ft.Column(
                spacing=2,
                controls=[row, ft.Text(field.help, size=TYPE.small, color=PALETTE.text_muted)],
            )
        return row

    def _build_group(self, field: ConfigFieldVM) -> ft.Control:
        """group：固定子字段递归渲染为带标题的缩进块。"""

        children = _with_dividers([self._build_field(sub) for sub in field.fields])
        body = ft.Column(children, spacing=12, tight=True)
        return ft.Column(
            spacing=8,
            controls=[
                ft.Text(field.label, size=TYPE.body_lg, weight=ft.FontWeight.W_600, color=PALETTE.text),
                ft.Container(body, padding=ft.padding.only(left=12)),
            ],
        )

    def _render_control(self, field: ConfigFieldVM) -> ft.Control:
        """经 WidgetRegistry 渲染叶子控件；无 renderer 时只读兜底。"""

        ctx = RenderContext(
            field=field,
            emit=lambda value, f=field: self._on_change(f.path, value),
            scheduler=self._scheduler,
            choices_registry=self._choices,
            safe_update=self.safe_update,
        )
        control = self._widgets.render(ctx)
        if control is None:
            return ft.Text(str(field.value), size=TYPE.body, color=PALETTE.text_muted)
        return control


def _with_dividers(controls: list[ft.Control]) -> list[ft.Control]:
    result: list[ft.Control] = []
    for index, control in enumerate(controls):
        if index == len(controls) - 1:
            result.append(control)
            continue
        result.append(
            ft.Container(
                content=control,
                padding=ft.padding.only(bottom=12),
                border=ft.border.only(bottom=ft.BorderSide(1, PALETTE.border)),
            )
        )
    return result
