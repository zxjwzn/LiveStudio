"""设置页面。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components import (
    MetricCard,
    StatusBadge,
    page_title,
    placeholder_grid,
    placeholder_region,
    styled_switch,
    styled_text_field,
)
from livestudio.gui.theme import Colors, Layout


class SettingsPage:
    """展示全局设置和配置文件入口。"""

    route = "settings"
    title = "设置"
    description = "配置文件、主题和运行参数"
    icon = ft.Icons.SETTINGS_OUTLINED

    def build(self) -> ft.Control:
        """构建设置页。"""

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=Layout.spacing_xl,
            controls=[
                placeholder_region(
                    title="页面标题区域",
                    description="设置页标题、主题状态和页面说明独立展示。",
                    content=page_title(
                        self.title,
                        "集中展示配置文件路径、主题信息和后续 GUI 行为偏好。",
                        actions=[
                            StatusBadge(
                                "粉白主题",
                                color=Colors.accent.hex,
                                background=Colors.accent.with_opacity(0.12),
                            ).build(),
                        ],
                    ),
                ),
                placeholder_region(
                    title="配置文件区域",
                    description="不同配置入口拆成独立槽位，避免路径信息互相挤压。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="VTube Studio 配置槽",
                                content=MetricCard(
                                    "VTube Studio 配置",
                                    "config/vtube_studio.yaml",
                                    "平台连接与认证配置",
                                    ft.Icons.ARTICLE_OUTLINED,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="音频流配置槽",
                                content=MetricCard(
                                    "音频流配置",
                                    "config/audio_stream.yaml",
                                    "音频路由与输入配置",
                                    ft.Icons.ARTICLE_OUTLINED,
                                    Colors.info.hex,
                                ).build(),
                                dense=True,
                            ),
                            placeholder_region(
                                title="模型配置目录槽",
                                content=MetricCard(
                                    "模型配置目录",
                                    "config/models/vtubestudio",
                                    "按模型自动生成配置",
                                    ft.Icons.FOLDER_OUTLINED,
                                    Colors.warning.hex,
                                ).build(),
                                dense=True,
                            ),
                        ],
                    ),
                ),
                placeholder_region(
                    title="界面偏好区域",
                    description="偏好开关和路径输入使用嵌套区域分离，后续可单独扩展。",
                    content=placeholder_grid(
                        [
                            placeholder_region(
                                title="启动偏好子区域",
                                content=ft.Row(
                                    wrap=True,
                                    spacing=Layout.spacing_lg,
                                    controls=[
                                        styled_switch(
                                            label="启动时自动连接 VTube Studio",
                                            value=False,
                                        ),
                                        styled_switch(
                                            label="启动时自动启用音频流",
                                            value=False,
                                        ),
                                        styled_switch(
                                            label="保存窗口布局",
                                            value=True,
                                        ),
                                    ],
                                ),
                                dense=True,
                                expand=True,
                            ),
                            placeholder_region(
                                title="模型路径子区域",
                                content=styled_text_field(
                                    label="模型配置目录",
                                    value="config/models/vtubestudio",
                                    read_only=True,
                                ),
                                dense=True,
                                width=420,
                            ),
                        ],
                    ),
                ),
            ],
        )
