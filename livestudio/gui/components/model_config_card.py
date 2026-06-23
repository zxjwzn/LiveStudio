"""可折叠模型配置卡片组件（P4）。

默认收起，展开时加载完整配置。内部各编辑分区也默认折叠，仅在用户展开时
才构建对应 UI 控件（懒渲染），避免一次性渲染所有字段导致卡顿。
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Callable

import flet as ft

from livestudio.utils.log import logger

from ..core.theme import PALETTE, TYPE
from ..core.view_models import ModelConfigSummaryVM

if TYPE_CHECKING:
    from ..bridge.platforms.base import PlatformAdapter
    from ..core.view_context import ViewContext


class _CollapsibleSection(ft.Container):
    """通用可折叠分区：标题 + 展开/收起箭头，内容懒构建。"""

    def __init__(
        self,
        title: str,
        build_content: Callable[[], ft.Control],
        *,
        expanded: bool = False,
    ) -> None:
        self._build_content = build_content
        self._expanded = expanded
        self._content_built = False

        self._icon = ft.Icon(
            ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE,
            color=PALETTE.text_muted,
        )
        self._header = ft.Container(
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(
                        title,
                        size=TYPE.body_lg,
                        weight=ft.FontWeight.W_600,
                        color=PALETTE.text,
                    ),
                    self._icon,
                ],
            ),
            on_click=self._toggle,
            ink=True,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        self._body = ft.Container(
            visible=expanded,
            padding=ft.padding.only(left=12, right=12, bottom=12),
        )

        super().__init__(
            bgcolor=PALETTE.surface_alt,
            border=ft.border.all(1, PALETTE.border),
            border_radius=ft.border_radius.all(8),
            content=ft.Column(spacing=0, controls=[self._header, self._body]),
        )

        if expanded:
            self._do_build()

    def _toggle(self, _e: ft.ControlEvent) -> None:
        self._expanded = not self._expanded
        self._icon.name = ft.Icons.EXPAND_LESS if self._expanded else ft.Icons.EXPAND_MORE

        if self._expanded and not self._content_built:
            self._do_build()

        self._body.visible = self._expanded
        with contextlib.suppress(Exception):
            self.update()

    def _do_build(self) -> None:
        self._body.content = self._build_content()
        self._content_built = True


class ModelConfigCard(ft.Container):
    """单个模型配置的可折叠卡片。"""

    def __init__(
        self,
        summary: ModelConfigSummaryVM,
        adapter: "PlatformAdapter",
        ctx: "ViewContext",
    ) -> None:
        self._summary = summary
        self._adapter = adapter
        self._ctx = ctx
        self._expanded = False
        self._loaded = False
        self._config_instance: Any = None
        self._dirty = False
        self._staged: dict[str, Any] = {}

        # 收起态 UI
        self._expand_icon = ft.Icon(ft.Icons.EXPAND_MORE, color=PALETTE.text_muted)
        self._title = ft.Text(
            summary.model_name,
            size=TYPE.body_lg,
            weight=ft.FontWeight.W_600,
            color=PALETTE.text,
        )
        self._subtitle = ft.Text(
            f"ID: {summary.model_id[:8]}…" if len(summary.model_id) > 8 else f"ID: {summary.model_id}",
            size=TYPE.caption,
            color=PALETTE.text_muted,
        )
        self._header = ft.Container(
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row([self._title, self._subtitle], spacing=12),
                    self._expand_icon,
                ],
            ),
            on_click=self._toggle_expand,
            ink=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        )

        self._body = ft.Container(
            visible=False,
            padding=ft.padding.only(left=16, right=16, bottom=16),
        )
        self._loading = ft.ProgressRing(width=20, height=20, visible=False)

        super().__init__(
            bgcolor=PALETTE.surface,
            border=ft.border.all(1, PALETTE.border),
            border_radius=ft.border_radius.all(12),
            content=ft.Column(
                spacing=0,
                controls=[self._header, self._loading, self._body],
            ),
        )

    def _toggle_expand(self, _e: ft.ControlEvent) -> None:
        self._expanded = not self._expanded
        self._expand_icon.name = ft.Icons.EXPAND_LESS if self._expanded else ft.Icons.EXPAND_MORE

        if self._expanded and not self._loaded:
            self._loading.visible = True
            self._body.visible = False
            self._do_load()
        else:
            self._body.visible = self._expanded

        self._safe_update()

    def _do_load(self) -> None:
        """异步加载模型配置。"""

        async def _load() -> None:
            try:
                config = await self._adapter.load_model_config_raw(self._summary.file_stem)
            except Exception:
                logger.exception("加载模型配置失败: {}", self._summary.file_stem)
                config = None

            self._loading.visible = False
            if config is None:
                self._body.content = ft.Text("加载失败", color=PALETTE.danger)
                self._body.visible = True
                self._safe_update()
                return

            self._config_instance = config
            self._loaded = True
            self._render_config(config)
            self._body.visible = True
            self._safe_update()

        if self.page is not None:
            self.page.run_task(_load)

    def _render_config(self, config: Any) -> None:
        """渲染所有编辑分区（各分区默认折叠、懒构建内容）。"""

        # 保存/重置按钮
        self._save_btn = ft.FilledButton(
            text="保存",
            icon=ft.Icons.SAVE,
            disabled=True,
            style=ft.ButtonStyle(bgcolor=PALETTE.primary, color=PALETTE.on_primary),
            on_click=self._on_save,
        )
        self._reset_btn = ft.OutlinedButton(
            text="重置",
            icon=ft.Icons.RESTART_ALT,
            on_click=self._on_reset,
        )
        self._status_text = ft.Text("", size=TYPE.caption, color=PALETTE.text_muted)

        sections: list[ft.Control] = [
            _CollapsibleSection(
                "动画控制器",
                lambda cfg=config: self._build_controllers_editor(cfg),
            ),
            _CollapsibleSection(
                "语义绑定",
                lambda cfg=config: self._build_bindings_editor(cfg),
            ),
            _CollapsibleSection(
                "平台参数范围",
                lambda cfg=config: self._build_specs_editor(cfg),
            ),
            _CollapsibleSection(
                "表情 AU",
                lambda cfg=config: self._build_expression_editor(cfg),
            ),
            ft.Row(
                [self._save_btn, self._reset_btn, self._status_text],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]
        self._body.content = ft.Column(spacing=12, controls=sections)

    # —— 各分区懒构建工厂 ——

    def _build_controllers_editor(self, config: Any) -> ft.Control:
        from ..bridge.schema_introspect import introspect_model
        from ..components.config_editor import ConfigEditor, default_widget_registry

        section_vm = introspect_model(
            config.controllers,
            section_id="controllers",
            title="动画控制器",
            path_prefix="controllers",
        )
        return ConfigEditor(
            fields=list(section_vm.fields),
            on_change=self._on_field_change,
            widget_registry=default_widget_registry(),
            choices_registry=(self._ctx.bridge.choices if self._ctx.bridge else None),
            scheduler=self._schedule,
        )

    def _build_bindings_editor(self, config: Any) -> ft.Control:
        from ..components.bindings_editor import BindingsEditor

        bindings_data = []
        if hasattr(config, "semantic_profile") and config.semantic_profile:
            bindings_data = [b.model_dump(mode="json") for b in config.semantic_profile.bindings]
        return BindingsEditor(
            bindings=bindings_data,
            on_change=self._on_bindings_change,
        )

    def _build_specs_editor(self, config: Any) -> ft.Control:
        from ..components.param_specs_editor import ParamSpecsEditor

        specs_data = []
        if hasattr(config, "parameter_specs"):
            specs_data = [s.model_dump(mode="json") for s in config.parameter_specs]
        return ParamSpecsEditor(
            specs=specs_data,
            on_change=self._on_specs_change,
        )

    def _build_expression_editor(self, config: Any) -> ft.Control:
        from ..components.expression_units_editor import ExpressionUnitsEditor

        semantic_units = []
        native_units = []
        if hasattr(config, "expression_profile") and config.expression_profile:
            semantic_units = [u.model_dump(mode="json") for u in config.expression_profile.semantic_units]
            native_units = [u.model_dump(mode="json") for u in config.expression_profile.native_units]
        return ExpressionUnitsEditor(
            semantic_units=semantic_units,
            native_units=native_units,
            on_change=self._on_expression_units_change,
        )

    # —— 改动回调 ——
    def _on_field_change(self, path: str, value: Any) -> None:
        self._staged[path] = value
        self._mark_dirty()

    def _on_bindings_change(self, bindings: list[dict]) -> None:
        self._staged["semantic_profile.bindings"] = bindings
        self._mark_dirty()

    def _on_specs_change(self, specs: list[dict]) -> None:
        self._staged["parameter_specs"] = specs
        self._mark_dirty()

    def _on_expression_units_change(self, semantic: list[dict], native: list[dict]) -> None:
        self._staged["expression_profile.semantic_units"] = semantic
        self._staged["expression_profile.native_units"] = native
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        if hasattr(self, "_save_btn"):
            self._save_btn.disabled = False
            self._safe_update()

    # —— 保存 / 重置 ——
    def _on_save(self, _e: ft.ControlEvent) -> None:
        async def _do_save() -> None:
            if self._config_instance is None:
                return
            data = self._config_instance.model_dump(mode="json", exclude_none=True)
            for path, value in self._staged.items():
                self._set_nested(data, path, value)
            try:
                await self._adapter.save_model_config_raw(self._summary.file_stem, data)
                self._dirty = False
                self._staged.clear()
                self._save_btn.disabled = True
                self._status_text.value = "已保存 ✓"
                self._status_text.color = PALETTE.success
                self._config_instance = await self._adapter.load_model_config_raw(self._summary.file_stem)
            except Exception:
                logger.exception("保存模型配置失败: {}", self._summary.file_stem)
                self._status_text.value = "保存失败"
                self._status_text.color = PALETTE.danger
            self._safe_update()

        if self.page is not None:
            self.page.run_task(_do_save)

    def _on_reset(self, _e: ft.ControlEvent) -> None:
        """重新从磁盘加载，丢弃内存改动。"""

        self._staged.clear()
        self._dirty = False
        self._loaded = False
        self._do_load()

    # —— 工具 ——
    @staticmethod
    def _set_nested(data: dict, path: str, value: Any) -> None:
        """按点分隔路径设置嵌套字典值。"""

        keys = path.split(".")
        target = data
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def _schedule(self, coro_factory: Any) -> None:
        if self.page is not None:
            self.page.run_task(coro_factory)

    def _safe_update(self) -> None:
        if self.page is not None:
            self.page.update()
