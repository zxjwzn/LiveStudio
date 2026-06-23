"""模型配置列表视图（P4 第二级）。

展示某个平台下所有模型配置文件，每个模型以可折叠卡片渲染。
顶部有返回按钮，点击返回平台卡片列表。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from livestudio.utils.log import logger

from ..components.model_config_card import ModelConfigCard
from ..core.mount_aware import MountAware, SubscriptionHost
from ..core.theme import PALETTE, TYPE

if TYPE_CHECKING:
    from ..bridge.platforms.base import PlatformAdapter
    from ..core.view_context import ViewContext


class ModelConfigsPanel(MountAware, SubscriptionHost, ft.Column):
    """某平台下所有模型配置的列表面板。"""

    def __init__(
        self,
        ctx: "ViewContext",
        platform_id: str,
        platform_name: str,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)
        self._init_subscriptions()
        self.ctx = ctx
        self._platform_id = platform_id
        self._platform_name = platform_name
        self._on_back = on_back
        self._cards_column = ft.Column(spacing=12)
        self._loading = ft.ProgressRing(width=24, height=24)

        back_btn = ft.TextButton(
            text="← 返回",
            on_click=lambda _e: self._on_back(),
            style=ft.ButtonStyle(color=PALETTE.primary_hover),
        )
        title = ft.Text(
            f"{platform_name} 模型配置",
            size=TYPE.title,
            weight=ft.FontWeight.W_600,
            color=PALETTE.text,
        )
        self.controls = [
            ft.Row([back_btn, title], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._loading,
            self._cards_column,
        ]

    def did_mount(self) -> None:
        self._load_configs()

    def will_unmount(self) -> None:
        self.release_subscriptions()

    def _load_configs(self) -> None:
        """异步加载模型配置列表。"""

        async def _do() -> None:
            adapter = self._get_adapter()
            if adapter is None:
                self._loading.visible = False
                self._cards_column.controls = [ft.Text("适配器不可用", size=TYPE.body, color=PALETTE.text_muted)]
                self.safe_update()
                return
            try:
                summaries = await adapter.list_model_configs()
            except Exception:
                logger.exception("枚举模型配置失败")
                summaries = []

            self._loading.visible = False
            if not summaries:
                self._cards_column.controls = [ft.Text("暂无模型配置文件", size=TYPE.body, color=PALETTE.text_muted)]
            else:
                self._cards_column.controls = [
                    ModelConfigCard(
                        summary=s,
                        adapter=adapter,
                        ctx=self.ctx,
                    )
                    for s in summaries
                ]
            self.safe_update()

        if self.page is not None:
            self.page.run_task(_do)

    def _get_adapter(self) -> "PlatformAdapter | None":
        bridge = self.ctx.bridge
        if bridge is None:
            return None
        return bridge.adapter(self._platform_id)
