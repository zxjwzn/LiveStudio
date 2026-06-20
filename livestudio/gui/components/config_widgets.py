"""内置配置控件渲染器。

把基础 value_type 渲染成 flet 控件，注册到 WidgetRegistry。每个 renderer
只认 RenderContext，自管理输入 -> emit 上报；动态下拉额外用 ctx 的
scheduler + choices_registry 异步拉取选项，无需编辑器开特例。

控件 key：
- switch   bool 开关
- text     str 文本框
- number   int/float 数值文本框（带类型与范围校验）
- dropdown enum 下拉（静态 choices 或 choices_source 动态源）

注册自定义控件（旋钮、颜色选择器等）= 写一个 (ctx) -> Control 并 register，
编辑器零改动。
"""

from __future__ import annotations

from typing import Any

import flet as ft

from livestudio.utils.log import logger

from ..core.theme import PALETTE, TYPE
from ..core.view_models import ChoiceVM
from ..core.widget_registry import RenderContext, WidgetRegistry


def render_switch(ctx: RenderContext) -> ft.Control:
    """bool -> Switch。"""

    return ft.Switch(
        value=bool(ctx.field.value),
        active_color=PALETTE.primary,
        on_change=lambda e: ctx.emit(e.control.value),
    )


def render_text(ctx: RenderContext) -> ft.Control:
    """str -> TextField（失焦/回车提交）。"""

    field = ctx.field
    return ft.TextField(
        value="" if field.value is None else str(field.value),
        width=220,
        dense=True,
        on_blur=lambda e: ctx.emit(e.control.value),
        on_submit=lambda e: ctx.emit(e.control.value),
    )


def render_number(ctx: RenderContext) -> ft.Control:
    """int/float -> 数值 TextField（失焦/回车提交，带数值校验）。"""

    field = ctx.field
    text_field = ft.TextField(
        value="" if field.value is None else str(field.value),
        width=160,
        dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    def _commit(_e: ft.ControlEvent) -> None:
        raw = (text_field.value or "").strip()
        if raw == "":
            text_field.error_text = None
            ctx.emit(None)
            ctx.safe_update()
            return
        try:
            value: Any = int(raw) if field.value_type == "int" else float(raw)
        except ValueError:
            text_field.error_text = "请输入数字"
            ctx.safe_update()
            return
        if field.min is not None and value < field.min:
            text_field.error_text = f"不得小于 {field.min:g}"
            ctx.safe_update()
            return
        if field.max is not None and value > field.max:
            text_field.error_text = f"不得大于 {field.max:g}"
            ctx.safe_update()
            return
        text_field.error_text = None
        ctx.emit(value)
        ctx.safe_update()

    text_field.on_blur = _commit
    text_field.on_submit = _commit
    return text_field


def render_dropdown(ctx: RenderContext) -> ft.Control:
    """enum -> Dropdown。静态 choices 直接铺；choices_source 动态源异步拉取。"""

    field = ctx.field
    dropdown = ft.Dropdown(
        value=None if field.value is None else str(field.value),
        width=220,
        dense=True,
        options=[ft.dropdown.Option(key=str(c.value), text=c.label) for c in field.choices],
        on_change=lambda e: ctx.emit(e.control.value),
    )
    if not field.choices_source:
        return dropdown

    # 动态源：占位 + 刷新按钮，挂载后异步拉取
    status = ft.Text("", size=TYPE.small, color=PALETTE.text_muted)

    async def _resolve() -> None:
        if ctx.choices_registry is None:
            return
        status.value = "加载中…"
        status.color = PALETTE.text_muted
        ctx.safe_update()
        try:
            choices = await ctx.choices_registry.resolve(field.choices_source)
        except Exception:
            logger.exception("动态下拉选项加载失败: {}", field.choices_source)
            status.value = "加载失败，点刷新重试"
            status.color = PALETTE.danger
            ctx.safe_update()
            return
        _apply_choices(dropdown, choices, field.value)
        status.value = "" if choices else "无可用项"
        status.color = PALETTE.text_muted
        ctx.safe_update()

    def _refresh(_e: ft.ControlEvent) -> None:
        if ctx.scheduler is not None:
            ctx.scheduler(_resolve)

    # 挂载即拉取一次
    if ctx.scheduler is not None:
        ctx.scheduler(_resolve)

    refresh = ft.IconButton(icon=ft.Icons.REFRESH, icon_size=TYPE.icon, tooltip="刷新", on_click=_refresh)
    return ft.Row([dropdown, refresh, status], spacing=6, tight=True)


def _apply_choices(dropdown: ft.Dropdown, choices: list[ChoiceVM], current: Any) -> None:
    """回填动态选项；当前值仍在列表里则保留选中。"""

    dropdown.options = [ft.dropdown.Option(key=str(c.value), text=c.label) for c in choices]
    keys = {str(c.value) for c in choices}
    if current is not None and str(current) in keys:
        dropdown.value = str(current)


def register_builtin_widgets(registry: WidgetRegistry) -> None:
    """把内置控件渲染器注册到 registry。"""

    registry.register("switch", render_switch)
    registry.register("text", render_text)
    registry.register("number", render_number)
    registry.register("dropdown", render_dropdown)
