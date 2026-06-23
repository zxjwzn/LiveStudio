"""仪表盘页（P3）。

聚合总览，所有卡片均由 Observable 实时驱动：
- 连接状态：订阅 platforms + active_platform_id
- 音频电平：订阅 audio_level（复用 AudioMeter）
- 动画控制器：订阅 controllers，每项一个 ControllerCard，启停/触发转发 bridge 适配器
- 快速表情：订阅 expressions，每个 ExpressionButton 触发表情解算
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ..components.audio_meter import AudioMeter
from ..components.controller_card import ControllerCard
from ..components.expression_button import ExpressionButton
from ..components.section import Section
from ..core.base_view import BaseView
from ..core.mount_aware import updates_ui
from ..core.theme import PALETTE, TYPE, connection_color
from ..core.view_models import (
    AudioLevelVM,
    ControllerVM,
    ExpressionVM,
    connection_label,
)

if TYPE_CHECKING:
    from ..bridge.platforms.base import PlatformAdapter


class DashboardView(BaseView):
    """仪表盘视图。"""

    def build_content(self) -> ft.Control:
        # —— 连接状态卡 ——
        self._conn_dot = ft.Container(width=12, height=12, border_radius=6, bgcolor=PALETTE.text_muted)
        self._conn_name = ft.Text("VTube Studio", size=TYPE.body_lg, weight=ft.FontWeight.W_600, color=PALETTE.text)
        self._conn_state = ft.Text("未连接", size=TYPE.body, color=PALETTE.text_muted)
        self._conn_endpoint = ft.Text("", size=TYPE.caption, color=PALETTE.text_muted)
        self._conn_model = ft.Text("", size=TYPE.caption, color=PALETTE.text_muted)
        connection_card = Section(
            "连接状态",
            ft.Column(
                spacing=6,
                controls=[
                    ft.Row([self._conn_dot, self._conn_name, self._conn_state], spacing=8),
                    self._conn_endpoint,
                    self._conn_model,
                ],
            ),
        )

        # —— 音频电平卡 ——
        self._audio_meter = AudioMeter()
        audio_card = Section("音频电平", self._audio_meter)

        # —— 动画控制器区 ——
        self._controllers_wrap = ft.Row(wrap=True, spacing=10, run_spacing=10)
        controllers_card = Section("动画控制器", self._controllers_wrap)

        # —— 快速表情区 ——
        self._expressions_wrap = ft.Row(wrap=True, spacing=8, run_spacing=8)
        expressions_card = Section("快速表情", self._expressions_wrap)

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text("仪表盘", size=TYPE.title, weight=ft.FontWeight.W_600, color=PALETTE.text),
                ft.Row(
                    spacing=16,
                    controls=[
                        ft.Container(connection_card, expand=True),
                        ft.Container(audio_card, expand=True),
                    ],
                ),
                controllers_card,
                expressions_card,
            ],
        )

    # PLACEHOLDER_BIND

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.platforms, lambda _v: self._refresh_connection())
        self.watch(self.state.active_platform_id, lambda _v: self._refresh_connection())
        self.watch(self.state.audio_level, self._on_audio_level)
        self.watch(self.state.controllers, self._on_controllers)
        self.watch(self.state.expressions, self._on_expressions)

    # —— 连接状态 ——
    @updates_ui
    def _refresh_connection(self) -> None:
        # 回退语义收敛在 AppState.active_platform_status：active_id 未命中时回退首个平台
        status = self.state.active_platform_status()
        if status is None:
            self._conn_dot.bgcolor = PALETTE.text_muted
            self._conn_state.value = "未连接"
            self._conn_state.color = PALETTE.text_muted
            self._conn_endpoint.value = ""
            self._conn_model.value = ""
            return
        self._conn_dot.bgcolor = connection_color(status.connection)
        self._conn_name.value = status.display_name
        self._conn_state.value = connection_label(status.connection)
        self._conn_state.color = PALETTE.text
        self._conn_endpoint.value = status.endpoint or ""
        self._conn_model.value = f"模型: {status.model_name}" if status.model_name else "模型: 未加载"

    # —— 音频电平 ——
    @updates_ui
    def _on_audio_level(self, level: AudioLevelVM) -> None:
        self._audio_meter.update_level(level)

    # —— 动画控制器 ——
    @updates_ui
    def _on_controllers(self, controllers: list[ControllerVM]) -> None:
        # 仅展示 idle 型控制器；oneshot（表情解算）由「快速表情」区驱动，不需启停
        idle = [vm for vm in controllers if vm.type != "oneshot"]
        self._controllers_wrap.controls = [
            ft.Container(width=200, content=ControllerCard(vm, on_toggle=self._toggle_controller))
            for vm in idle
        ] or [self._empty_text("未连接，暂无控制器")]

    def _toggle_controller(self, vm: ControllerVM, enabled: bool) -> None:
        adapter = self._adapter()
        if adapter is None:
            return
        self.run_intent(lambda: adapter.set_controller_enabled(vm.key, enabled))

    # —— 快速表情 ——
    @updates_ui
    def _on_expressions(self, expressions: list[ExpressionVM]) -> None:
        self._expressions_wrap.controls = [
            ExpressionButton(vm, on_trigger=self._trigger_expression) for vm in expressions
        ] or [self._empty_text("未连接，暂无可用表情")]

    def _trigger_expression(self, vm: ExpressionVM) -> None:
        adapter = self._adapter()
        if adapter is None:
            return
        self.run_intent(lambda: adapter.trigger_expression(vm.key))

    # —— 工具 ——
    def _empty_text(self, text: str) -> ft.Control:
        """列表区为空时的统一占位文案。"""

        return ft.Text(text, size=TYPE.body, color=PALETTE.text_muted)

    def _adapter(self) -> "PlatformAdapter | None":
        """取当前激活平台的 bridge 适配器；bridge 不存在时返回 None。"""

        bridge = self.ctx.bridge
        if bridge is None:
            return None
        return bridge.active_adapter()
