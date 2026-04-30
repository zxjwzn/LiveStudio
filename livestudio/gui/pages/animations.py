"""动画控制页面。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components import (
    MetricCard,
    StatusBadge,
    page_title,
    placeholder_grid,
    placeholder_region,
    styled_switch,
)
from livestudio.gui.theme import Colors, Layout


class AnimationsPage:
    """展示动画控制器启用状态和关键参数入口。"""

    route = "animations"
    title = "动画控制"
    description = "眨眼、呼吸、摇摆、表情与嘴型同步"
    icon = ft.Icons.AUTO_FIX_HIGH_OUTLINED

    def build(self) -> ft.Control:
        """构建动画控制页。"""

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=Layout.spacing_xl,
            controls=[
                placeholder_region(
                    title="页面标题区域",
                    description="动画页说明和控制器总状态独立展示。",
                    content=page_title(
                        self.title,
                        "按当前模型配置管理各动画控制器，后续可逐项展开参数编辑。",
                        actions=[
                            StatusBadge(
                                "5 个控制器",
                                color=Colors.accent.hex,
                                background=Colors.accent.with_opacity(0.12),
                            ).build(),
                        ],
                    ),
                ),
                placeholder_region(
                    title="控制器概览区域",
                    description="常用控制器指标分别占用独立槽位。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="眨眼概览槽",
                                content=MetricCard(
                                    "眨眼",
                                    "启用",
                                    "随机间隔自然眨眼",
                                    ft.Icons.REMOVE_RED_EYE_OUTLINED,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="呼吸概览槽",
                                content=MetricCard(
                                    "呼吸",
                                    "启用",
                                    "周期性呼吸参数",
                                    ft.Icons.AIR,
                                    Colors.info.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="身体摇摆槽",
                                content=MetricCard(
                                    "身体摇摆",
                                    "启用",
                                    "身体与眼睛跟随",
                                    ft.Icons.ACCESSIBILITY_NEW,
                                    Colors.warning.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="嘴型同步槽",
                                content=MetricCard(
                                    "嘴型同步",
                                    "启用",
                                    "基于音频响度驱动",
                                    ft.Icons.RECORD_VOICE_OVER_OUTLINED,
                                ).build(),
                                dense=True,
                            ),
                        ],
                    ),
                ),
                placeholder_region(
                    title="控制器配置区域",
                    description="每个控制器行都是嵌套占位子区域，可后续独立扩展参数面板。",
                    content=ft.Column(
                        spacing=Layout.spacing_md,
                        controls=[
                            placeholder_region(
                                title="眨眼控制器子区域",
                                content=self._controller_row(
                                    "眨眼控制器",
                                    "blink",
                                    True,
                                    "最小/最大间隔、闭眼与睁眼时长",
                                ),
                                dense=True,
                            ),
                            placeholder_region(
                                title="呼吸控制器子区域",
                                content=self._controller_row(
                                    "呼吸控制器",
                                    "breathing",
                                    True,
                                    "呼吸上下限、吸气与呼气时长",
                                ),
                                dense=True,
                            ),
                            placeholder_region(
                                title="身体摇摆控制器子区域",
                                content=self._controller_row(
                                    "身体摇摆控制器",
                                    "body_swing",
                                    True,
                                    "X/Z 摇摆范围、持续时间、眼睛跟随",
                                ),
                                dense=True,
                            ),
                            placeholder_region(
                                title="嘴部表情控制器子区域",
                                content=self._controller_row(
                                    "嘴部表情控制器",
                                    "mouth_expression",
                                    True,
                                    "微笑与开口的随机表情范围",
                                ),
                                dense=True,
                            ),
                            placeholder_region(
                                title="嘴型同步控制器子区域",
                                content=self._controller_row(
                                    "嘴型同步控制器",
                                    "mouth_sync",
                                    True,
                                    "静音门限、语音上限、平滑与优先级",
                                ),
                                dense=True,
                            ),
                        ],
                    ),
                ),
            ],
        )

    def _controller_row(
        self,
        title: str,
        key: str,
        enabled: bool,
        description: str,
    ) -> ft.Container:
        return ft.Container(
            padding=Layout.padding_md,
            border_radius=Layout.radius_md,
            bgcolor=Colors.surface_variant.hex,
            border=ft.border.all(1, Colors.border.hex),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(
                                title,
                                weight=ft.FontWeight.BOLD,
                                color=Colors.text_primary.hex,
                            ),
                            ft.Text(
                                f"{key} · {description}",
                                size=12,
                                color=Colors.text_secondary.hex,
                            ),
                        ],
                    ),
                    styled_switch(value=enabled),
                ],
            ),
        )
