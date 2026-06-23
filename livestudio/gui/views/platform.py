"""平台页（P4）。

第一级：平台卡片列表，每张卡片展示连接状态 + 连接/断开控制 + LAN 发现 + 模型配置入口。
内部子视图切换到第二级「模型配置列表」时，替换容器内容并显示返回按钮。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ..components.section import Section
from ..core.base_view import BaseView
from ..core.mount_aware import updates_ui
from ..core.theme import PALETTE, TYPE, connection_color
from ..core.view_models import (
    ConnectionState,
    DiscoveredEndpointVM,
    PlatformStatusVM,
    connection_label,
)

if TYPE_CHECKING:
    from ..bridge.platforms.base import PlatformAdapter


class PlatformView(BaseView):
    """平台视图 — 内部两级：平台卡片列表 / 模型配置列表。"""

    def build_content(self) -> ft.Control:
        self._container = ft.Container(expand=True)
        # 每个平台的 endpoint 输入框持久引用，避免状态刷新时丢失用户输入
        self._endpoint_fields: dict[str, ft.TextField] = {}
        # 记录上次从后端同步到输入框的 endpoint 值，仅后端真正改变时才覆盖
        self._last_synced_endpoint: dict[str, str] = {}
        self._show_platforms()
        return self._container

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.platforms, lambda _v: self._show_platforms())
        self.watch(self.state.active_platform_id, lambda _v: self._show_platforms())

    # —— 第一级：平台卡片列表 ——
    @updates_ui
    def _show_platforms(self) -> None:
        cards: list[ft.Control] = []
        for status in self.state.platforms.value:
            cards.append(self._build_platform_card(status))
        if not cards:
            cards.append(ft.Text("暂无已注册平台", size=TYPE.body, color=PALETTE.text_muted))
        self._container.content = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text("平台", size=TYPE.title, weight=ft.FontWeight.W_600, color=PALETTE.text),
                *cards,
            ],
        )

    def _build_platform_card(self, status: PlatformStatusVM) -> ft.Control:
        """构建单个平台的卡片。"""

        # 连接状态
        dot = ft.Container(
            width=12,
            height=12,
            border_radius=6,
            bgcolor=connection_color(status.connection),
        )
        conn_text = ft.Text(
            connection_label(status.connection),
            size=TYPE.body,
            color=PALETTE.text,
        )
        platform_name = ft.Text(
            status.display_name,
            size=TYPE.body_lg,
            weight=ft.FontWeight.W_600,
            color=PALETTE.text,
        )

        # Endpoint 显示
        endpoint_text = ft.Text(
            status.endpoint or "未配置地址",
            size=TYPE.caption,
            color=PALETTE.text_muted,
        )
        model_text = ft.Text(
            f"模型: {status.model_name}" if status.model_name else "模型: 未加载",
            size=TYPE.caption,
            color=PALETTE.text_muted,
        )

        # Endpoint 输入框 — 持久化引用，不随 rebuild 丢失用户输入
        pid = status.platform_id
        if pid not in self._endpoint_fields:
            self._endpoint_fields[pid] = ft.TextField(
                value=status.endpoint or "",
                label="Endpoint",
                hint_text="ws://localhost:8001",
                dense=True,
                width=280,
            )
            self._last_synced_endpoint[pid] = status.endpoint or ""
        endpoint_field = self._endpoint_fields[pid]
        # 仅当后端 endpoint 相对上次同步值发生变化时才覆盖输入框
        # （避免状态刷新时覆盖用户正在编辑的内容）
        backend_ep = status.endpoint or ""
        if backend_ep != self._last_synced_endpoint.get(pid, ""):
            endpoint_field.value = backend_ep
            self._last_synced_endpoint[pid] = backend_ep

        # 操作按钮 — 连接和断开分开
        is_connected = status.connection in (ConnectionState.CONNECTED, ConnectionState.RECONNECTING)
        is_connecting = status.connection == ConnectionState.CONNECTING

        connect_btn = ft.FilledButton(
            text="连接中…" if is_connecting else "连接",
            icon=ft.Icons.LINK,
            disabled=is_connecting or is_connected,
            style=ft.ButtonStyle(bgcolor=PALETTE.primary, color=PALETTE.on_primary),
            on_click=lambda _e, _pid=pid, ef=endpoint_field: self._on_connect(_pid, ef.value or ""),
        )

        disconnect_btn = ft.OutlinedButton(
            text="断开",
            icon=ft.Icons.LINK_OFF,
            disabled=not (is_connected or is_connecting),
            style=ft.ButtonStyle(color=PALETTE.danger),
            on_click=lambda _e, _pid=pid: self._on_disconnect(_pid),
        )

        discover_btn = ft.OutlinedButton(
            text="LAN 发现",
            icon=ft.Icons.WIFI_FIND,
            on_click=lambda _e, _pid=pid, ef=endpoint_field: self._on_discover(_pid, ef),
        )

        config_btn = ft.OutlinedButton(
            text="模型配置 →",
            icon=ft.Icons.TUNE,
            on_click=lambda _e, _pid=pid: self._show_model_configs(_pid),
        )

        body = ft.Column(
            spacing=12,
            controls=[
                ft.Row([dot, platform_name, conn_text], spacing=8),
                ft.Row([endpoint_text, model_text], spacing=16),
                ft.Row(
                    spacing=12,
                    controls=[endpoint_field, connect_btn, disconnect_btn, discover_btn],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                ft.Row([config_btn]),
            ],
        )
        return Section(status.display_name, body)

    # —— 连接操作 ——
    def _on_connect(self, platform_id: str, endpoint: str) -> None:
        adapter = self._get_adapter(platform_id)
        if adapter is None:
            return
        self.run_intent(lambda: adapter.connect(endpoint or None))

    def _on_disconnect(self, platform_id: str) -> None:
        adapter = self._get_adapter(platform_id)
        if adapter is None:
            return
        self.run_intent(lambda: adapter.disconnect())

    # —— LAN 发现 ——
    def _on_discover(self, platform_id: str, endpoint_field: ft.TextField) -> None:
        adapter = self._get_adapter(platform_id)
        if adapter is None:
            return

        # 立即弹出"搜索中"对话框
        self._discover_dlg = ft.AlertDialog(
            title=ft.Text("LAN 发现", size=TYPE.heading),
            content=ft.Row(
                [
                    ft.ProgressRing(width=20, height=20),
                    ft.Text("正在搜索局域网中的设备…", size=TYPE.body, color=PALETTE.text_muted),
                ],
                spacing=12,
            ),
            actions=[
                ft.TextButton(
                    "取消",
                    on_click=lambda _e: self.page.close(self._discover_dlg) if self.page else None,
                ),
            ],
        )
        if self.page is not None:
            self.page.open(self._discover_dlg)

        async def _do_discover() -> None:
            results = await adapter.discover()
            # 关闭搜索中对话框，弹出结果
            if self.page is not None:
                self.page.close(self._discover_dlg)
            self._show_discover_dialog(results, endpoint_field)

        self.run_intent(_do_discover)

    def _show_discover_dialog(self, results: list[DiscoveredEndpointVM], endpoint_field: ft.TextField) -> None:
        if self.page is None:
            return

        def _select(ep: DiscoveredEndpointVM) -> None:
            endpoint_field.value = ep.address
            self.safe_update()
            if self.page is not None:
                self.page.close(dlg)

        if not results:
            content = ft.Text("未发现任何可用端点", size=TYPE.body, color=PALETTE.text_muted)
        else:
            content = ft.Column(
                spacing=8,
                controls=[
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.ROUTER, color=PALETTE.primary),
                        title=ft.Text(ep.name, size=TYPE.body),
                        subtitle=ft.Text(ep.address, size=TYPE.caption),
                        on_click=lambda _e, ep=ep: _select(ep),
                    )
                    for ep in results
                ],
            )

        dlg = ft.AlertDialog(
            title=ft.Text("LAN 发现结果", size=TYPE.heading),
            content=content,
            actions=[
                ft.TextButton("关闭", on_click=lambda _e: self.page.close(dlg) if self.page else None),
            ],
        )
        self.page.open(dlg)

    # —— 第二级入口 ——
    def _show_model_configs(self, platform_id: str) -> None:
        from .model_configs import ModelConfigsPanel

        # 从 platforms 状态中查找 display_name
        status = self.state.platform_status(platform_id)
        platform_name = status.display_name if status else platform_id

        panel = ModelConfigsPanel(
            ctx=self.ctx,
            platform_id=platform_id,
            platform_name=platform_name,
            on_back=self._show_platforms,
        )
        self._container.content = panel
        self.safe_update()

    # —— 工具 ——
    def _get_adapter(self, platform_id: str) -> "PlatformAdapter | None":
        bridge = self.ctx.bridge
        if bridge is None:
            return None
        return bridge.adapter(platform_id)
