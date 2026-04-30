"""音频流页面。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components import (
    MetricCard,
    StatusBadge,
    page_title,
    placeholder_grid,
    placeholder_region,
    styled_dropdown,
    styled_progress_bar,
    styled_switch,
)
from livestudio.gui.theme import Colors, Layout


class AudioPage:
    """展示音频路由与输入电平。"""

    route = "audio"
    title = "音频流"
    description = "麦克风、TTS、实时电平和路由配置"
    icon = ft.Icons.MIC_NONE_OUTLINED

    def build(self) -> ft.Control:
        """构建音频流页面。"""

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=Layout.spacing_xl,
            controls=[
                placeholder_region(
                    title="页面标题区域",
                    description="音频页说明和当前音频源状态独立展示。",
                    content=page_title(
                        self.title,
                        "集中管理当前活动音频源，并为嘴型同步提供音频分析数据。",
                        actions=[
                            StatusBadge(
                                "默认麦克风",
                                color=Colors.info.hex,
                                background=Colors.info.with_opacity(0.12),
                            ).build(),
                        ],
                    ),
                ),
                placeholder_region(
                    title="音频指标区域",
                    description="活动源、RMS 和 Peak 指标分别放入独立占位槽。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="活动源槽",
                                content=MetricCard(
                                    "活动源",
                                    "Microphone",
                                    "来自 audio_stream.yaml",
                                    ft.Icons.SETTINGS_VOICE_OUTLINED,
                                    Colors.info.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="RMS 电平槽",
                                content=MetricCard(
                                    "RMS 电平",
                                    "0.00",
                                    "后续接入实时订阅队列",
                                    ft.Icons.SPEED,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="Peak 峰值槽",
                                content=MetricCard(
                                    "Peak 峰值",
                                    "0.00",
                                    "用于观察爆音和过载",
                                    ft.Icons.SIGNAL_CELLULAR_ALT,
                                    Colors.warning.hex,
                                ).build(),
                                dense=True,
                            ),
                        ],
                    ),
                ),
                placeholder_region(
                    title="实时音频工作区",
                    description="内部嵌套电平监控区和路由控制区，互不干扰。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="电平监控子区域",
                                content=ft.Column(
                                    spacing=Layout.spacing_lg,
                                    controls=[
                                        self._level_row("RMS", 0.0),
                                        self._level_row("Peak", 0.0),
                                    ],
                                ),
                                dense=True,
                                width=420,
                            ),
                            placeholder_region(
                                title="音频路由控制子区域",
                                content=ft.Row(
                                    wrap=True,
                                    spacing=Layout.spacing_lg,
                                    controls=[
                                        styled_dropdown(
                                            label="活动音频源",
                                            value="microphone",
                                            width=260,
                                            options=[
                                                ft.DropdownOption(
                                                    "microphone",
                                                    text="麦克风",
                                                ),
                                                ft.DropdownOption("tts", text="TTS"),
                                            ],
                                        ),
                                        styled_switch(
                                            label="启动音频流",
                                            value=False,
                                        ),
                                        styled_switch(
                                            label="用于嘴型同步",
                                            value=True,
                                        ),
                                    ],
                                ),
                                dense=True,
                                expand=True,
                            ),
                        ],
                    ),
                ),
            ],
        )

    def _level_row(self, label: str, value: float) -> ft.Row:
        return ft.Row(
            spacing=Layout.spacing_md,
            controls=[
                ft.Text(label, width=64, color=Colors.text_secondary.hex),
                styled_progress_bar(
                    expand=True,
                    value=value,
                ),
                ft.Text(f"{value:.2f}", width=48, color=Colors.text_secondary.hex),
            ],
        )
