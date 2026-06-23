"""平台参数范围列表编辑器（P4）。

编辑 parameter_specs：每行一个 PlatformParameterSpec（name / minimum / maximum），
支持增删改。
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable

import flet as ft

from ..core.theme import PALETTE, TYPE


class ParamSpecsEditor(ft.Column):
    """平台参数范围列表编辑器。"""

    def __init__(
        self,
        specs: list[dict[str, Any]],
        on_change: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        super().__init__(spacing=8, tight=True)
        self._specs = [dict(s) for s in specs]
        self._on_change = on_change
        self._rebuild()

    def _rebuild(self) -> None:
        rows: list[ft.Control] = []
        for idx, spec in enumerate(self._specs):
            rows.append(self._build_row(idx, spec))

        add_btn = ft.TextButton(
            text="添加参数",
            icon=ft.Icons.ADD,
            on_click=self._on_add,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
        )
        self.controls = [*rows, add_btn]

    def _build_row(self, idx: int, spec: dict[str, Any]) -> ft.Control:
        name_field = ft.TextField(
            value=spec.get("name", ""),
            label="参数名",
            width=200,
            dense=True,
            on_blur=lambda e, i=idx: self._update(i, "name", e.control.value),
            on_submit=lambda e, i=idx: self._update(i, "name", e.control.value),
        )

        min_field = ft.TextField(
            value=str(spec.get("minimum", 0)),
            label="最小值",
            width=100,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e, i=idx: self._update_num(i, "minimum", e.control.value),
            on_submit=lambda e, i=idx: self._update_num(i, "minimum", e.control.value),
        )

        max_field = ft.TextField(
            value=str(spec.get("maximum", 0)),
            label="最大值",
            width=100,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e, i=idx: self._update_num(i, "maximum", e.control.value),
            on_submit=lambda e, i=idx: self._update_num(i, "maximum", e.control.value),
        )

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=TYPE.icon,
            icon_color=PALETTE.danger,
            tooltip="删除",
            on_click=lambda _e, i=idx: self._on_delete(i),
        )

        return ft.Row(
            controls=[name_field, min_field, max_field, delete_btn],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _update(self, idx: int, key: str, value: Any) -> None:
        if 0 <= idx < len(self._specs):
            self._specs[idx][key] = value
            self._emit()

    def _update_num(self, idx: int, key: str, raw: str) -> None:
        try:
            value = float(raw)
        except ValueError:
            return
        if 0 <= idx < len(self._specs):
            self._specs[idx][key] = value
            self._emit()

    def _on_add(self, _e: ft.ControlEvent) -> None:
        self._specs.append({"name": "", "minimum": -30.0, "maximum": 30.0})
        self._rebuild()
        self._emit()
        self._safe_update()

    def _on_delete(self, idx: int) -> None:
        if 0 <= idx < len(self._specs):
            self._specs.pop(idx)
            self._rebuild()
            self._emit()
            self._safe_update()

    def _emit(self) -> None:
        self._on_change(self._specs)

    def _safe_update(self) -> None:
        with contextlib.suppress(Exception):
            self.update()
