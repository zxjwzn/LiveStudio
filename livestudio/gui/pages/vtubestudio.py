"""VTube Studio 页面。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components import (
    MetricCard,
    StatusBadge,
    action_card,
    page_title,
    placeholder_grid,
    placeholder_region,
)
from livestudio.gui.theme import Colors, Layout


class VTubeStudioPage:
    """展示 VTube Studio 平台连接与模型状态。"""

    route = "vtubestudio"
    title = "VTube Studio"
    description = "连接、认证、模型和表情状态"
    icon = ft.Icons.HUB_OUTLINED

    def build(self) -> ft.Control:
        """构建 VTube Studio 页面。"""

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=Layout.spacing_xl,
            controls=[
                placeholder_region(
                    title="页面标题区域",
                    description="平台页标题、连接状态徽章和页面说明独占此区域。",
                    content=page_title(
                        self.title,
                        "管理 VTube Studio 平台连接、插件认证和模型级配置。",
                        actions=[
                            StatusBadge(
                                "未连接",
                                color=Colors.warning.hex,
                                background=Colors.warning.with_opacity(0.14),
                            ).build(),
                        ],
                    ),
                ),
                placeholder_region(
                    title="平台状态区域",
                    description="连接、认证和模型配置各自占用独立槽位。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="连接状态槽",
                                content=MetricCard(
                                    "连接状态",
                                    "离线",
                                    "等待 WebSocket 连接",
                                    ft.Icons.LINK_OFF,
                                    Colors.warning.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="认证状态槽",
                                content=MetricCard(
                                    "认证状态",
                                    "待认证",
                                    "缺少或尚未校验插件 Token",
                                    ft.Icons.VERIFIED_USER_OUTLINED,
                                    Colors.info.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="模型配置槽",
                                content=MetricCard(
                                    "模型配置",
                                    "自动加载",
                                    "按模型 ID 写入独立 YAML",
                                    ft.Icons.DESCRIPTION_OUTLINED,
                                ).build(),
                                dense=True,
                            ),
                        ],
                    ),
                ),
                placeholder_region(
                    title="平台操作区域",
                    description="所有平台动作按钮集中在此区域，避免与状态区互相挤压。",
                    content=ft.Column(
                        spacing=Layout.spacing_lg,
                        controls=[
                            action_card(
                                title="发现 VTube Studio API",
                                description="监听局域网 API 广播，用于后续自动填充连接信息。",
                                icon=ft.Icons.TRAVEL_EXPLORE,
                                button_text="扫描",
                            ),
                            action_card(
                                title="请求插件认证",
                                description="当没有 Token 或 Token 失效时，引导用户在 VTube Studio 中授权。",
                                icon=ft.Icons.KEY_OUTLINED,
                                button_text="申请 Token",
                            ),
                            action_card(
                                title="同步当前模型表情",
                                description="读取当前模型表情列表，并保存激活状态到模型配置。",
                                icon=ft.Icons.FACE_RETOUCHING_NATURAL,
                                button_text="同步表情",
                            ),
                        ],
                    ),
                ),
            ],
        )
