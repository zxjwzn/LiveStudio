"""运行总览页。"""

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


class DashboardPage:
    """展示 LiveStudio 当前核心服务概况。"""

    route = "dashboard"
    title = "运行总览"
    description = "统一查看连接、音频、动画与模型状态"
    icon = ft.Icons.DASHBOARD_OUTLINED

    def build(self) -> ft.Control:
        """构建运行总览页。"""

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=Layout.spacing_xl,
            controls=[
                placeholder_region(
                    title="页面标题区域",
                    description="页面说明、状态徽章和后续页面级快捷动作固定放在此区域。",
                    content=page_title(
                        self.title,
                        "聚合展示 LiveStudio 的关键运行指标，后续可接入真实状态快照。",
                        actions=[
                            StatusBadge(
                                "状态快照",
                                color=Colors.info.hex,
                                background=Colors.info.with_opacity(0.12),
                            ).build(),
                        ],
                    ),
                ),
                placeholder_region(
                    title="关键指标区域",
                    description="每个指标卡片先放入独立占位框，再由外层区域统一换行排列。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="VTube Studio 状态槽",
                                content=MetricCard(
                                    "VTube Studio",
                                    "未连接",
                                    "等待连接与认证",
                                    ft.Icons.HUB_OUTLINED,
                                    Colors.warning.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="音频流状态槽",
                                content=MetricCard(
                                    "音频流",
                                    "麦克风",
                                    "默认音频源已配置",
                                    ft.Icons.MIC_NONE_OUTLINED,
                                    Colors.info.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="动画运行时槽",
                                content=MetricCard(
                                    "动画运行时",
                                    "5 个控制器",
                                    "眨眼、呼吸、摇摆、表情、嘴型同步",
                                    ft.Icons.AUTO_FIX_HIGH_OUTLINED,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="当前模型槽",
                                content=MetricCard(
                                    "当前模型",
                                    "待加载",
                                    "连接后自动同步模型配置",
                                    ft.Icons.PERSON_OUTLINE,
                                    Colors.text_secondary.hex,
                                ).build(),
                                dense=True,
                            ),
                        ],
                    ),
                ),
                placeholder_region(
                    title="推荐启动流程区域",
                    description="流程步骤在区域内纵向排列，互不影响其它页面区域。",
                    content=ft.Column(
                        spacing=Layout.spacing_lg,
                        controls=[
                            action_card(
                                title="启动 VTube Studio 连接",
                                description="完成 WebSocket 连接、插件认证和模型配置加载。",
                                icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                                button_text="准备接入",
                            ),
                            action_card(
                                title="检查音频输入",
                                description="确认麦克风或 TTS 音频源可用，并观察实时电平。",
                                icon=ft.Icons.GRAPHIC_EQ,
                                button_text="查看音频页",
                            ),
                            action_card(
                                title="启用动画控制器",
                                description="按模型配置加载眨眼、呼吸、摇摆和嘴型同步控制器。",
                                icon=ft.Icons.TUNE,
                                button_text="查看动画页",
                            ),
                        ],
                    ),
                ),
            ],
        )
