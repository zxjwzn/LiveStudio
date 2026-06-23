"""表情 AU 列表编辑器（P4）。

编辑 expression_profile 下的 semantic_units 和 native_units。
每个 AU 以子卡片展示：
- targets 逐行展示 [action下拉] [min] [max]，带添加/删除按钮
- emotions 逐行展示 [emotion下拉] [weight]，带添加/删除按钮
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable

import flet as ft

from ..core.theme import PALETTE, TYPE

_EMOTIONS = ["joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral"]

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


class ExpressionUnitsEditor(ft.Column):
    """表情 AU 列表编辑器，分语义 AU / 原生 AU 两区。"""

    def __init__(
        self,
        semantic_units: list[dict[str, Any]],
        native_units: list[dict[str, Any]],
        on_change: Callable[[list[dict[str, Any]], list[dict[str, Any]]], None],
    ) -> None:
        super().__init__(spacing=12, tight=True)
        self._semantic = [_deep_copy_unit(u) for u in semantic_units]
        self._native = [_deep_copy_unit(u) for u in native_units]
        self._on_change = on_change
        self._rebuild()

    def _rebuild(self) -> None:
        semantic_section = self._build_semantic_section()
        native_section = self._build_native_section()
        self.controls = [semantic_section, native_section]

    # ── 语义 AU ─────────────────────────────────────────────

    def _build_semantic_section(self) -> ft.Control:
        cards: list[ft.Control] = []
        for idx, unit in enumerate(self._semantic):
            cards.append(self._build_semantic_card(idx, unit))

        add_btn = ft.TextButton(
            text="+ 添加语义 AU",
            icon=ft.Icons.ADD,
            on_click=self._add_semantic,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
        )
        return ft.Column(
            spacing=8,
            controls=[
                ft.Text(
                    "语义 AU",
                    size=TYPE.body_lg,
                    weight=ft.FontWeight.W_600,
                    color=PALETTE.text,
                ),
                *cards,
                add_btn,
            ],
        )

    def _build_semantic_card(self, idx: int, unit: dict[str, Any]) -> ft.Control:
        """单个语义 AU 的编辑卡片。"""

        id_field = ft.TextField(
            value=unit.get("id", ""),
            label="ID",
            width=160,
            dense=True,
            on_blur=lambda e, i=idx: self._update_semantic(i, "id", e.control.value),
            on_submit=lambda e, i=idx: self._update_semantic(i, "id", e.control.value),
        )

        enabled_switch = ft.Switch(
            value=unit.get("enabled", True),
            active_color=PALETTE.primary,
            on_change=lambda e, i=idx: self._update_semantic(i, "enabled", e.control.value),
        )

        easing_field = ft.TextField(
            value=unit.get("easing", "linear"),
            label="Easing",
            width=120,
            dense=True,
            on_blur=lambda e, i=idx: self._update_semantic(i, "easing", e.control.value),
            on_submit=lambda e, i=idx: self._update_semantic(i, "easing", e.control.value),
        )

        threshold_field = ft.TextField(
            value=str(unit.get("activation_threshold", 0.05)),
            label="阈值",
            width=80,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e, i=idx: self._update_semantic_num(i, "activation_threshold", e.control.value),
            on_submit=lambda e, i=idx: self._update_semantic_num(i, "activation_threshold", e.control.value),
        )

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=TYPE.icon,
            icon_color=PALETTE.danger,
            tooltip="删除此 AU",
            on_click=lambda _e, i=idx: self._delete_semantic(i),
        )

        # Targets 列表编辑
        targets_col = self._build_targets_editor(idx, unit.get("targets", []))

        # Emotions 列表编辑
        emotions_col = self._build_emotions_editor(idx, unit.get("emotions", {}))

        return ft.Container(
            bgcolor=PALETTE.surface_alt,
            border_radius=ft.border_radius.all(8),
            padding=ft.padding.all(10),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        [
                            id_field,
                            easing_field,
                            threshold_field,
                            ft.Text("启用:", size=TYPE.caption),
                            enabled_switch,
                            delete_btn,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    targets_col,
                    emotions_col,
                ],
            ),
        )

    def _build_targets_editor(self, unit_idx: int, targets: list[dict[str, Any]]) -> ft.Control:
        """构建单个 AU 的 targets 逐行编辑区。"""

        rows: list[ft.Control] = []
        for t_idx, target in enumerate(targets):
            action_dd = ft.Dropdown(
                value=target.get("action", ""),
                width=160,
                dense=True,
                label="语义动作",
                options=[ft.dropdown.Option(a) for a in _SEMANTIC_ACTIONS],
                on_change=lambda e, ui=unit_idx, ti=t_idx: self._update_target(ui, ti, "action", e.control.value),
            )
            min_field = ft.TextField(
                value=str(target.get("min_value", 0.0)),
                label="最小值",
                width=80,
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_blur=lambda e, ui=unit_idx, ti=t_idx: self._update_target_num(ui, ti, "min_value", e.control.value),
                on_submit=lambda e, ui=unit_idx, ti=t_idx: self._update_target_num(ui, ti, "min_value", e.control.value),
            )
            max_field = ft.TextField(
                value=str(target.get("max_value", 1.0)),
                label="最大值",
                width=80,
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_blur=lambda e, ui=unit_idx, ti=t_idx: self._update_target_num(ui, ti, "max_value", e.control.value),
                on_submit=lambda e, ui=unit_idx, ti=t_idx: self._update_target_num(ui, ti, "max_value", e.control.value),
            )
            del_btn = ft.IconButton(
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                icon_size=14,
                icon_color=PALETTE.danger,
                tooltip="删除此 target",
                on_click=lambda _e, ui=unit_idx, ti=t_idx: self._delete_target(ui, ti),
            )
            rows.append(
                ft.Row(
                    [action_dd, min_field, max_field, del_btn],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        add_btn = ft.TextButton(
            text="+ Target",
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
            on_click=lambda _e, ui=unit_idx: self._add_target(ui),
        )

        return ft.Column(
            spacing=4,
            controls=[
                ft.Text("Targets:", size=TYPE.caption, color=PALETTE.text_muted),
                *rows,
                add_btn,
            ],
        )

    def _build_emotions_editor(self, unit_idx: int, emotions: dict[str, Any]) -> ft.Control:
        """构建单个 AU 的 emotions 逐行编辑区。"""

        rows: list[ft.Control] = []
        emotion_items = list(emotions.items())
        for e_idx, (emotion_key, weight) in enumerate(emotion_items):
            emo_dd = ft.Dropdown(
                value=emotion_key,
                width=140,
                dense=True,
                label="情绪",
                options=[ft.dropdown.Option(e) for e in _EMOTIONS],
                on_change=lambda e, ui=unit_idx, ei=e_idx: self._update_emotion_key(ui, ei, e.control.value),
            )
            weight_field = ft.TextField(
                value=str(weight),
                label="权重",
                width=80,
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_blur=lambda e, ui=unit_idx, ei=e_idx: self._update_emotion_weight(ui, ei, e.control.value),
                on_submit=lambda e, ui=unit_idx, ei=e_idx: self._update_emotion_weight(ui, ei, e.control.value),
            )
            del_btn = ft.IconButton(
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                icon_size=14,
                icon_color=PALETTE.danger,
                tooltip="删除此 emotion",
                on_click=lambda _e, ui=unit_idx, ei=e_idx: self._delete_emotion(ui, ei),
            )
            rows.append(
                ft.Row(
                    [emo_dd, weight_field, del_btn],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        add_btn = ft.TextButton(
            text="+ Emotion",
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
            on_click=lambda _e, ui=unit_idx: self._add_emotion(ui),
        )

        return ft.Column(
            spacing=4,
            controls=[
                ft.Text("Emotions:", size=TYPE.caption, color=PALETTE.text_muted),
                *rows,
                add_btn,
            ],
        )

    # ── 语义 AU 操作 ───────────────────────────────────────

    def _update_semantic(self, idx: int, key: str, value: Any) -> None:
        if 0 <= idx < len(self._semantic):
            self._semantic[idx][key] = value
            self._emit()

    def _update_semantic_num(self, idx: int, key: str, raw: str) -> None:
        try:
            value = float(raw)
        except ValueError:
            return
        if 0 <= idx < len(self._semantic):
            self._semantic[idx][key] = value
            self._emit()

    def _add_semantic(self, _e: ft.ControlEvent) -> None:
        self._semantic.append(
            {
                "id": "",
                "enabled": True,
                "targets": [],
                "emotions": {},
                "easing": "linear",
                "activation_threshold": 0.05,
            }
        )
        self._rebuild()
        self._emit()
        self._safe_update()

    def _delete_semantic(self, idx: int) -> None:
        if 0 <= idx < len(self._semantic):
            self._semantic.pop(idx)
            self._rebuild()
            self._emit()
            self._safe_update()

    # ── Target 操作 ────────────────────────────────────────

    def _update_target(self, unit_idx: int, target_idx: int, key: str, value: Any) -> None:
        targets = self._semantic[unit_idx].get("targets", [])
        if 0 <= target_idx < len(targets):
            targets[target_idx][key] = value
            self._emit()

    def _update_target_num(self, unit_idx: int, target_idx: int, key: str, raw: str) -> None:
        try:
            value = float(raw)
        except ValueError:
            return
        targets = self._semantic[unit_idx].get("targets", [])
        if 0 <= target_idx < len(targets):
            targets[target_idx][key] = value
            self._emit()

    def _add_target(self, unit_idx: int) -> None:
        if 0 <= unit_idx < len(self._semantic):
            targets = self._semantic[unit_idx].setdefault("targets", [])
            targets.append({"action": "", "min_value": 0.0, "max_value": 1.0})
            self._rebuild()
            self._emit()
            self._safe_update()

    def _delete_target(self, unit_idx: int, target_idx: int) -> None:
        targets = self._semantic[unit_idx].get("targets", [])
        if 0 <= target_idx < len(targets):
            targets.pop(target_idx)
            self._rebuild()
            self._emit()
            self._safe_update()

    # ── Emotion 操作 ───────────────────────────────────────

    def _update_emotion_key(self, unit_idx: int, emotion_idx: int, new_key: str) -> None:
        emotions = self._semantic[unit_idx].get("emotions", {})
        items = list(emotions.items())
        if 0 <= emotion_idx < len(items):
            # 替换 key：删旧加新（保留顺序通过重建字典）
            new_emotions = {}
            for i, (k, v) in enumerate(items):
                if i == emotion_idx:
                    new_emotions[new_key] = v
                else:
                    new_emotions[k] = v
            self._semantic[unit_idx]["emotions"] = new_emotions
            self._emit()

    def _update_emotion_weight(self, unit_idx: int, emotion_idx: int, raw: str) -> None:
        try:
            weight = float(raw)
        except ValueError:
            return
        emotions = self._semantic[unit_idx].get("emotions", {})
        items = list(emotions.items())
        if 0 <= emotion_idx < len(items):
            key = items[emotion_idx][0]
            emotions[key] = weight
            self._emit()

    def _add_emotion(self, unit_idx: int) -> None:
        if 0 <= unit_idx < len(self._semantic):
            emotions = self._semantic[unit_idx].setdefault("emotions", {})
            # 找一个尚未使用的 emotion key
            used = set(emotions.keys())
            new_key = next((e for e in _EMOTIONS if e not in used), "joy")
            emotions[new_key] = 0.5
            self._rebuild()
            self._emit()
            self._safe_update()

    def _delete_emotion(self, unit_idx: int, emotion_idx: int) -> None:
        emotions = self._semantic[unit_idx].get("emotions", {})
        items = list(emotions.items())
        if 0 <= emotion_idx < len(items):
            key = items[emotion_idx][0]
            del emotions[key]
            self._rebuild()
            self._emit()
            self._safe_update()

    # ── 原生 AU ─────────────────────────────────────────────

    def _build_native_section(self) -> ft.Control:
        cards: list[ft.Control] = []
        for idx, unit in enumerate(self._native):
            cards.append(self._build_native_card(idx, unit))

        add_btn = ft.TextButton(
            text="+ 添加原生 AU",
            icon=ft.Icons.ADD,
            on_click=self._add_native,
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
        )
        return ft.Column(
            spacing=8,
            controls=[
                ft.Text(
                    "原生 AU",
                    size=TYPE.body_lg,
                    weight=ft.FontWeight.W_600,
                    color=PALETTE.text,
                ),
                *cards,
                add_btn,
            ],
        )

    def _build_native_card(self, idx: int, unit: dict[str, Any]) -> ft.Control:
        id_field = ft.TextField(
            value=unit.get("id", ""),
            label="ID",
            width=140,
            dense=True,
            on_blur=lambda e, i=idx: self._update_native(i, "id", e.control.value),
            on_submit=lambda e, i=idx: self._update_native(i, "id", e.control.value),
        )

        platform_field = ft.TextField(
            value=unit.get("platform", ""),
            label="平台",
            width=120,
            dense=True,
            on_blur=lambda e, i=idx: self._update_native(i, "platform", e.control.value),
            on_submit=lambda e, i=idx: self._update_native(i, "platform", e.control.value),
        )

        ref_field = ft.TextField(
            value=unit.get("native_ref", ""),
            label="原生引用",
            width=200,
            dense=True,
            on_blur=lambda e, i=idx: self._update_native(i, "native_ref", e.control.value),
            on_submit=lambda e, i=idx: self._update_native(i, "native_ref", e.control.value),
        )

        enabled_switch = ft.Switch(
            value=unit.get("enabled", True),
            active_color=PALETTE.primary,
            on_change=lambda e, i=idx: self._update_native(i, "enabled", e.control.value),
        )

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=TYPE.icon,
            icon_color=PALETTE.danger,
            tooltip="删除",
            on_click=lambda _e, i=idx: self._delete_native(i),
        )

        return ft.Container(
            bgcolor=PALETTE.surface_alt,
            border_radius=ft.border_radius.all(8),
            padding=ft.padding.all(10),
            content=ft.Row(
                [
                    id_field,
                    platform_field,
                    ref_field,
                    ft.Text("启用:", size=TYPE.caption),
                    enabled_switch,
                    delete_btn,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
        )

    def _update_native(self, idx: int, key: str, value: Any) -> None:
        if 0 <= idx < len(self._native):
            self._native[idx][key] = value
            self._emit()

    def _add_native(self, _e: ft.ControlEvent) -> None:
        self._native.append(
            {
                "id": "",
                "enabled": True,
                "platform": "vtubestudio",
                "native_ref": "",
                "regions": [],
                "emotions": {},
                "activation_threshold": 0.05,
            }
        )
        self._rebuild()
        self._emit()
        self._safe_update()

    def _delete_native(self, idx: int) -> None:
        if 0 <= idx < len(self._native):
            self._native.pop(idx)
            self._rebuild()
            self._emit()
            self._safe_update()

    # ── 通用 ────────────────────────────────────────────────

    def _emit(self) -> None:
        self._on_change(self._semantic, self._native)

    def _safe_update(self) -> None:
        with contextlib.suppress(Exception):
            self.update()


def _deep_copy_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """深拷贝单个 AU 字典，确保 targets/emotions 是独立副本。"""

    result = dict(unit)
    if "targets" in result:
        result["targets"] = [dict(t) for t in result["targets"]]
    if "emotions" in result:
        result["emotions"] = dict(result["emotions"])
    return result
