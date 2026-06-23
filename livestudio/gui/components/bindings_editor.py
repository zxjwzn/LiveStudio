"""语义绑定列表编辑器（P4）。

编辑 semantic_profile.bindings：每行一个 SemanticActionBinding，
展示 action → platform_params 映射，支持增删改。
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable

import flet as ft

from ..core.theme import PALETTE, TYPE

# 可选的语义动作列表（作为 action 下拉选项）
_SEMANTIC_ACTIONS: list[str] = [
    "brow.height",
    "brow.height.left",
    "brow.height.right",
    "eye.open",
    "eye.open.left",
    "eye.open.right",
    "eye.gaze.x",
    "eye.gaze.y",
    "mouth.open",
    "mouth.smile",
    "mouth.x",
    "mouth.y",
    "head.yaw",
    "head.pitch",
    "head.roll",
]


class BindingsEditor(ft.Column):
    """语义绑定列表编辑器。"""

    def __init__(
        self,
        bindings: list[dict[str, Any]],
        on_change: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        super().__init__(spacing=8, tight=True)
        self._bindings = [dict(b) for b in bindings]  # 深拷贝
        self._on_change = on_change
        self._rebuild()

    def _rebuild(self) -> None:
        """重建所有行。"""

        rows: list[ft.Control] = []
        for idx, binding in enumerate(self._bindings):
            rows.append(self._build_row(idx, binding))

        add_btn = ft.TextButton(
            text="+ 添加绑定",
            icon=ft.Icons.ADD,
            on_click=self._on_add,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
        )
        self.controls = [*rows, add_btn]

    def _build_row(self, idx: int, binding: dict[str, Any]) -> ft.Control:
        """构建单行绑定编辑。"""

        action_dropdown = ft.Dropdown(
            value=binding.get("action", ""),
            width=180,
            dense=True,
            options=[ft.dropdown.Option(a) for a in _SEMANTIC_ACTIONS],
            on_change=lambda e, i=idx: self._update_field(i, "action", e.control.value),
        )

        params_value = binding.get("platform_params", [])
        params_field = ft.TextField(
            value=", ".join(params_value) if isinstance(params_value, list) else str(params_value),
            label="平台参数",
            hint_text="逗号分隔多个参数名",
            width=240,
            dense=True,
            on_blur=lambda e, i=idx: self._update_params(i, e.control.value),
            on_submit=lambda e, i=idx: self._update_params(i, e.control.value),
        )

        curve_field = ft.TextField(
            value=binding.get("curve", "linear"),
            label="曲线",
            width=100,
            dense=True,
            on_blur=lambda e, i=idx: self._update_field(i, "curve", e.control.value),
            on_submit=lambda e, i=idx: self._update_field(i, "curve", e.control.value),
        )

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=TYPE.icon,
            icon_color=PALETTE.danger,
            tooltip="删除",
            on_click=lambda _e, i=idx: self._on_delete(i),
        )

        return ft.Row(
            controls=[action_dropdown, ft.Text("→", color=PALETTE.text_muted), params_field, curve_field, delete_btn],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )

    def _update_field(self, idx: int, key: str, value: Any) -> None:
        if 0 <= idx < len(self._bindings):
            self._bindings[idx][key] = value
            self._emit()

    def _update_params(self, idx: int, raw: str) -> None:
        """逗号分隔字符串 → 列表。"""

        params = [p.strip() for p in raw.split(",") if p.strip()]
        if 0 <= idx < len(self._bindings):
            self._bindings[idx]["platform_params"] = params
            self._emit()

    def _on_add(self, _e: ft.ControlEvent) -> None:
        self._bindings.append({"action": "", "platform_params": [], "curve": "linear"})
        self._rebuild()
        self._emit()
        self._safe_update()

    def _on_delete(self, idx: int) -> None:
        if 0 <= idx < len(self._bindings):
            self._bindings.pop(idx)
            self._rebuild()
            self._emit()
            self._safe_update()

    def _emit(self) -> None:
        self._on_change(self._bindings)

    def _safe_update(self) -> None:
        with contextlib.suppress(Exception):
            self.update()
